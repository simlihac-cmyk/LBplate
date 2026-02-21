import re

KOREAN_WORD_PATTERN = re.compile(r'^[가-힣]{2,}$')

# 형태소 분석기 없이 조사 결합형을 줄이기 위한 보수적 휴리스틱
MULTI_CHAR_JOSA_SUFFIXES = (
    '으로부터', '으로서', '으로써', '에게서', '이라도', '이라서', '인데도', '인데요',
    '처럼', '까지', '부터', '보다', '한테', '에게', '에서', '으로', '라고', '이며',
    '인데', '이나', '라도', '밖에', '조차', '마저'
)

# 단일 글자 조사 중 오검출 위험이 상대적으로 낮은 것만 사용
SINGLE_CHAR_JOSA_SUFFIXES = (
    '은', '는', '을', '를', '와', '과', '에', '로', '도', '만', '랑'
)

EXCLUDED_STANDALONE_FUNCTION_WORDS = set(MULTI_CHAR_JOSA_SUFFIXES) | {
    '또는', '및', '또한',
}

NON_DICTIONARY_SUFFIXES = (
    # 공손/문장 종결형
    '습니까', '습니다', '니다', '입니다', '하세요', '세요', '네요', '군요', '아요', '어요', '해요',
    # 활용/어미 결합형
    '인가요', '라고요', '인데요', '지만', '니까', '면서', '거나', '도록', '려고',
    # 서술 활용형 (기본형 명사/동사/형용사에서 제외)
    '한다', '준다', '했다', '된다', '됐다', '였다', '있는', '없는',
)

NON_DICTIONARY_DA_SUFFIXES = (
    '한다', '준다', '된다', '했다', '됐다', '였다', '갔다', '왔다', '봤다',
)

DA_EXCLUDE_JONGSUNG_INDEXES = {20}  # ㅆ
DA_ALLOWLIST = {'있다', '없다'}


def get_jongsung_index(ch):
    code = ord(ch) - 0xAC00
    if code < 0 or code > 11171:
        return 0
    return code % 28


def looks_like_conjugated_da_form(word):
    if not word.endswith('다') or len(word) < 2:
        return False

    if word in DA_ALLOWLIST:
        return False

    if word.endswith(NON_DICTIONARY_DA_SUFFIXES):
        return True

    prev = word[-2]
    jongsung_idx = get_jongsung_index(prev)
    if jongsung_idx in DA_EXCLUDE_JONGSUNG_INDEXES:
        return True

    return False


def looks_like_josa_form(word, vocabulary):
    for suffix in MULTI_CHAR_JOSA_SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        # 예: 때부터 -> 때 + 부터
        if len(stem) < 1:
            continue
        return True

    for suffix in SINGLE_CHAR_JOSA_SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[:-1]
        # 한 글자 어근으로 인한 오검출(예: 마을/가을) 최소화
        if len(stem) < 2:
            continue
        if stem in vocabulary:
            return True

    return False


def is_clean_korean_word(word, vocabulary):
    if not KOREAN_WORD_PATTERN.fullmatch(word):
        return False
    if word in EXCLUDED_STANDALONE_FUNCTION_WORDS:
        return False
    if word.endswith(NON_DICTIONARY_SUFFIXES):
        return False
    if looks_like_conjugated_da_form(word):
        return False
    if looks_like_josa_form(word, vocabulary):
        return False
    return True
