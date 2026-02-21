import datetime
import json
import os
import re
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from gensim.models import KeyedVectors

from core.kkomantle_filters import is_clean_korean_word


OPENDICT_SEARCH_URL = "https://opendict.korean.go.kr/api/search"
STDICT_SEARCH_URL = "https://stdict.korean.go.kr/api/search"
WORD_KEY_PATTERN = re.compile(r'[\s\-\^]')


def normalize_dict_word(word):
    if not isinstance(word, str):
        return ""
    return WORD_KEY_PATTERN.sub("", word).strip()


def extract_channel_items(payload):
    if not isinstance(payload, dict):
        return 0, []
    channel = payload.get("channel")
    if not isinstance(channel, dict):
        return 0, []

    total = channel.get("total", 0)
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 0

    items = channel.get("item") or []
    if isinstance(items, dict):
        items = [items]
    elif not isinstance(items, list):
        items = []
    return total, items


def payload_has_exact_word(payload, target_word):
    target = normalize_dict_word(target_word)
    if not target:
        return False

    total, items = extract_channel_items(payload)
    if total <= 0:
        return False
    if not items:
        return True

    for item in items:
        if not isinstance(item, dict):
            continue
        candidates = []

        direct_word = item.get("word")
        if isinstance(direct_word, str):
            candidates.append(direct_word)

        word_info = item.get("word_info")
        if isinstance(word_info, dict):
            info_word = word_info.get("word")
            if isinstance(info_word, str):
                candidates.append(info_word)

        for candidate in candidates:
            if normalize_dict_word(candidate) == target:
                return True

    return False


class Command(BaseCommand):
    help = "Build Kkomantle whitelist by validating model candidates against NIKL dictionary APIs."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=getattr(settings, "KKOMANTLE_WHITELIST_PATH", "core/data/kkomantle_whitelist.txt"),
            help="Output whitelist file path",
        )
        parser.add_argument(
            "--cache-path",
            default="core/data/kkomantle_nikl_cache.json",
            help="Cache file for per-word dictionary lookup results",
        )
        parser.add_argument(
            "--model-path",
            default=getattr(settings, "WORD2VEC_MODEL_PATH", ""),
            help="Word2Vec .vec path",
        )
        parser.add_argument(
            "--model-limit",
            type=int,
            default=getattr(settings, "WORD2VEC_LIMIT", 300000),
            help="Maximum vectors loaded from model",
        )
        parser.add_argument(
            "--candidate-topn",
            type=int,
            default=max(5000, getattr(settings, "KKOMANTLE_MODEL_CANDIDATE_TOPN", 5000)),
            help="Number of high-frequency model tokens to inspect before dictionary validation",
        )
        parser.add_argument(
            "--source",
            choices=("opendict", "stdict", "both"),
            default="both",
            help="Dictionary sources used for validation",
        )
        parser.add_argument("--opendict-key", default="", help="Open dictionary API key")
        parser.add_argument("--stdict-key", default="", help="Standard dictionary API key")
        parser.add_argument(
            "--timeout",
            type=float,
            default=8.0,
            help="HTTP timeout seconds",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.03,
            help="Sleep between API calls to avoid throttling",
        )
        parser.add_argument(
            "--save-every",
            type=int,
            default=200,
            help="Save cache every N processed words",
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=2,
            help="Max retries per API request on transient network errors",
        )
        parser.add_argument(
            "--retry-sleep",
            type=float,
            default=0.2,
            help="Sleep seconds between retries",
        )
        parser.add_argument(
            "--max-words",
            type=int,
            default=0,
            help="Stop after N filtered candidate words (0 = all)",
        )
        parser.add_argument(
            "--force-refresh",
            action="store_true",
            help="Ignore cached lookup results and query APIs again",
        )

    def handle(self, *args, **options):
        model_path = options["model_path"]
        if not model_path or not os.path.exists(model_path):
            raise CommandError(f"Model file not found: {model_path}")

        source = options["source"]
        opendict_enabled = source in ("opendict", "both")
        stdict_enabled = source in ("stdict", "both")

        shared_key = os.getenv("NIKL_API_KEY", "")
        opendict_key = options["opendict_key"] or os.getenv("NIKL_OPENDICT_API_KEY", "") or shared_key
        stdict_key = options["stdict_key"] or os.getenv("NIKL_STDICT_API_KEY", "") or shared_key

        if opendict_enabled and not opendict_key:
            raise CommandError("Missing Open Dictionary API key. Set --opendict-key or NIKL_OPENDICT_API_KEY.")
        if stdict_enabled and not stdict_key:
            raise CommandError("Missing Standard Dictionary API key. Set --stdict-key or NIKL_STDICT_API_KEY.")

        self.stdout.write(self.style.NOTICE("Loading model..."))
        model = KeyedVectors.load_word2vec_format(
            model_path,
            binary=False,
            limit=options["model_limit"],
        )
        vocabulary = set(model.key_to_index)

        raw_candidates = model.index_to_key[: options["candidate_topn"]]
        filtered_candidates = [w for w in raw_candidates if is_clean_korean_word(w, vocabulary)]

        max_words = options["max_words"]
        if max_words > 0:
            filtered_candidates = filtered_candidates[:max_words]

        self.stdout.write(
            self.style.NOTICE(
                f"Candidates prepared: raw={len(raw_candidates)} filtered={len(filtered_candidates)}"
            )
        )

        cache_path = options["cache_path"]
        cache = self._load_cache(cache_path)
        cache_results = cache.setdefault("results", {})

        timeout = options["timeout"]
        sleep_sec = max(0.0, options["sleep"])
        save_every = max(1, options["save_every"])
        max_retries = max(0, options["max_retries"])
        retry_sleep = max(0.0, options["retry_sleep"])
        force_refresh = options["force_refresh"]

        approved = []
        queried = 0
        cache_hits = 0

        for idx, word in enumerate(filtered_candidates, start=1):
            cached_value = cache_results.get(word)
            if cached_value is not None and not force_refresh:
                exists = bool(cached_value)
                cache_hits += 1
            else:
                exists = self._exists_in_nikl(
                    word=word,
                    timeout=timeout,
                    opendict_key=opendict_key if opendict_enabled else "",
                    stdict_key=stdict_key if stdict_enabled else "",
                    max_retries=max_retries,
                    retry_sleep=retry_sleep,
                )
                cache_results[word] = bool(exists)
                queried += 1
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

            if exists:
                approved.append(word)

            if idx % save_every == 0:
                self._save_cache(cache_path, cache)
                self.stdout.write(
                    f"[{idx}/{len(filtered_candidates)}] approved={len(approved)} queried={queried} cache_hits={cache_hits}"
                )

        self._save_cache(cache_path, cache)
        self._write_whitelist(
            output_path=options["output"],
            approved_words=approved,
            source=source,
            model_path=model_path,
            model_limit=options["model_limit"],
            candidate_topn=options["candidate_topn"],
            filtered_count=len(filtered_candidates),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. approved={len(approved)} queried={queried} cache_hits={cache_hits} output={options['output']}"
            )
        )

    def _exists_in_nikl(
        self,
        word,
        timeout,
        opendict_key="",
        stdict_key="",
        max_retries=2,
        retry_sleep=0.2,
    ):
        if opendict_key:
            if self._query_with_retries(
                OPENDICT_SEARCH_URL,
                opendict_key,
                word,
                timeout,
                max_retries=max_retries,
                retry_sleep=retry_sleep,
            ):
                return True
        if stdict_key:
            if self._query_with_retries(
                STDICT_SEARCH_URL,
                stdict_key,
                word,
                timeout,
                max_retries=max_retries,
                retry_sleep=retry_sleep,
            ):
                return True
        return False

    def _query_with_retries(self, endpoint, api_key, word, timeout, max_retries=2, retry_sleep=0.2):
        for attempt in range(max_retries + 1):
            try:
                return self._query_search_api(endpoint, api_key, word, timeout)
            except requests.RequestException:
                if attempt >= max_retries:
                    return False
                if retry_sleep > 0:
                    time.sleep(retry_sleep * (attempt + 1))
        return False

    def _query_search_api(self, endpoint, api_key, word, timeout):
        params = {
            "key": api_key,
            "req_type": "json",
            "q": word,
            "advanced": "y",
            "target": "1",
            "method": "exact",
            "type1": "word",
            "start": "1",
            "num": "10",
        }
        response = requests.get(endpoint, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return payload_has_exact_word(payload, word)

    def _load_cache(self, cache_path):
        if not os.path.exists(cache_path):
            return {"version": 1, "results": {}}

        try:
            with open(cache_path, "r", encoding="utf-8") as fp:
                loaded = json.load(fp)
            if not isinstance(loaded, dict):
                return {"version": 1, "results": {}}
            if not isinstance(loaded.get("results"), dict):
                loaded["results"] = {}
            return loaded
        except Exception:
            return {"version": 1, "results": {}}

    def _save_cache(self, cache_path, cache_data):
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fp:
            json.dump(cache_data, fp, ensure_ascii=False, indent=2, sort_keys=True)

    def _write_whitelist(
        self,
        output_path,
        approved_words,
        source,
        model_path,
        model_limit,
        candidate_topn,
        filtered_count,
    ):
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        generated_at = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        header = [
            "# Kkomantle whitelist (NIKL dictionary validated)",
            f"# source={source}",
            f"# generated_at_utc={generated_at}",
            f"# model_path={model_path}",
            f"# model_limit={model_limit}",
            f"# candidate_topn={candidate_topn}",
            f"# filtered_candidates={filtered_count}",
            f"# approved_words={len(approved_words)}",
        ]

        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(header))
            fp.write("\n")
            for word in approved_words:
                fp.write(f"{word}\n")
