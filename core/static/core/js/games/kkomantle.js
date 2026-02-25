const input = document.getElementById('wordInput');
const list = document.getElementById('guessList');
const submitBtn = document.getElementById('submitBtn');
const hintBtn = document.getElementById('hintBtn');
const surrenderBtn = document.getElementById('surrenderBtn');
const successArea = document.getElementById('successArea');
const statusText = document.getElementById('statusText');
const guessForm = document.getElementById('guessForm');
const shareBtn = document.getElementById('shareBtn');
const successTitle = document.getElementById('successTitle');
const successMessage = document.getElementById('successMessage');
const answerLine = document.getElementById('answerLine');
const hintArea = document.getElementById('hintArea');
const hintList = document.getElementById('hintList');
const relatedArea = document.getElementById('relatedArea');
const relatedList = document.getElementById('relatedList');
const summaryCount = document.getElementById('summaryCount');
const summaryBestScore = document.getElementById('summaryBestScore');
const summaryHotCount = document.getElementById('summaryHotCount');
const historyBtn = document.getElementById('historyBtn');
const historyModal = document.getElementById('historyModal');
const historyCloseBtn = document.getElementById('historyCloseBtn');
const historyMeta = document.getElementById('historyMeta');
const historyList = document.getElementById('historyList');

const HINT_RANKS = [200, 100, 50];

let guesses = [];
let isGameOver = false;
let isBusy = false;
let hintStep = 0;
let guessSequence = 0;
let latestGuessId = null;
let historyLoading = false;

function setStatus(message, isError = false) {
    if (!statusText) return;
    statusText.innerText = message;
    statusText.style.color = isError ? '#d93025' : '#666';
}

function updateHintButtonLabel() {
    if (!hintBtn) return;
    hintBtn.innerText = `힌트 보기 (${hintStep}/${HINT_RANKS.length})`;
}

function setBusy(nextBusy) {
    isBusy = nextBusy;
    submitBtn.disabled = nextBusy || isGameOver;

    if (hintBtn) {
        const hintExhausted = hintStep >= HINT_RANKS.length;
        hintBtn.disabled = nextBusy || isGameOver || hintExhausted;
    }

    if (surrenderBtn) {
        surrenderBtn.disabled = nextBusy || isGameOver;
    }
}

function getSortedGuesses() {
    return [...guesses].sort((a, b) => {
        if (a.id === latestGuessId) return -1;
        if (b.id === latestGuessId) return 1;
        if (b.score !== a.score) return b.score - a.score;
        return b.id - a.id;
    });
}

function setGameOverState() {
    isGameOver = true;
    input.disabled = true;
    setBusy(false);
    submitBtn.disabled = true;
    if (hintBtn) hintBtn.disabled = true;
    if (surrenderBtn) surrenderBtn.disabled = true;
}

function showRelatedWords(words) {
    if (!relatedArea || !relatedList) return;

    relatedList.innerHTML = '';
    if (!Array.isArray(words) || words.length === 0) {
        relatedArea.style.display = 'none';
        return;
    }

    words.forEach((item) => {
        const li = document.createElement('li');
        const score = Number(item.score);
        const safeScore = Number.isFinite(score) ? score.toFixed(2) : '-';
        li.textContent = `#${item.rank} ${item.word} (유사도 ${safeScore})`;
        relatedList.appendChild(li);
    });

    relatedArea.style.display = 'block';
}

function finishGame({ solved, answer, similarWords }) {
    setGameOverState();

    successArea.style.display = 'block';
    answerLine.textContent = answer ? `정답: ${answer}` : '';

    if (solved) {
        successTitle.textContent = '🎉 정답입니다!';
        successMessage.textContent = `${guesses.length}번 만에 맞추셨네요!`;
        if (shareBtn) shareBtn.style.display = 'inline-flex';

        if (window.trackEvent) {
            window.trackEvent('game_finish', {
                event_category: 'games',
                event_label: 'kkomantle',
                attempts: guesses.length,
            });
        }
    } else {
        successTitle.textContent = '🙌 이번 판은 여기까지';
        successMessage.textContent = '포기하고 정답을 확인했습니다.';
        if (shareBtn) shareBtn.style.display = 'none';
    }

    showRelatedWords(similarWords);
}

if (guessForm) {
    guessForm.addEventListener('submit', (e) => {
        e.preventDefault();
        submitGuess();
    });
}

if (shareBtn) {
    shareBtn.addEventListener('click', shareResult);
}

if (hintBtn) {
    hintBtn.addEventListener('click', requestHint);
}

if (surrenderBtn) {
    surrenderBtn.addEventListener('click', surrenderGame);
}

if (historyBtn) {
    historyBtn.addEventListener('click', openHistoryModal);
}

if (historyCloseBtn) {
    historyCloseBtn.addEventListener('click', closeHistoryModal);
}

if (historyModal) {
    historyModal.addEventListener('click', (event) => {
        if (event.target === historyModal) {
            closeHistoryModal();
        }
    });
}

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!historyModal || historyModal.classList.contains('hidden')) return;
    closeHistoryModal();
});

async function submitGuess() {
    if (isGameOver || isBusy) return;

    const word = input.value.trim();
    if (!word) return;

    if (guesses.some((g) => g.word === word)) {
        setStatus('이미 입력한 단어입니다.', true);
        input.value = '';
        return;
    }

    setBusy(true);
    setStatus('단어를 확인하는 중입니다...');

    try {
        const response = await fetch(GAME_CONFIG.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': GAME_CONFIG.csrfToken,
            },
            body: JSON.stringify({ word }),
        });

        const data = await response.json();

        if (!response.ok || data.result === 'fail' || data.result === 'error') {
            setStatus(data.message || '처리 중 오류가 발생했습니다.', true);
        } else {
            addGuess(word, data.score, data.rank, data.result === 'correct');

            if (data.result === 'correct') {
                setStatus('오늘의 단어를 찾았습니다!');
                finishGame({
                    solved: true,
                    answer: data.answer || word,
                    similarWords: data.similar_words || [],
                });
            } else {
                setStatus('좋아요! 다음 단어도 시도해보세요.');
            }
        }

        input.value = '';
        input.focus();
    } catch (err) {
        console.error(err);
        setStatus('서버 연결에 실패했습니다.', true);
    } finally {
        if (!isGameOver) {
            setBusy(false);
        }
    }
}

function addGuess(word, score, rank, isCorrect) {
    guessSequence += 1;
    latestGuessId = guessSequence;

    guesses.push({
        id: guessSequence,
        word,
        score: Number(score),
        rank,
        isCorrect,
    });

    renderList();
}

function updateSummary(sortedGuesses) {
    if (!summaryCount || !summaryBestScore || !summaryHotCount) return;

    summaryCount.textContent = String(guesses.length);
    if (sortedGuesses.length === 0) {
        summaryBestScore.textContent = '-';
        summaryHotCount.textContent = '0';
        return;
    }

    const bestScore = sortedGuesses.reduce((max, item) => Math.max(max, Number(item.score) || 0), 0);
    const hotCount = sortedGuesses.filter((item) => typeof item.rank === 'number' && item.rank <= 1000).length;
    summaryBestScore.textContent = Number(bestScore).toFixed(2);
    summaryHotCount.textContent = String(hotCount);
}

function renderList() {
    list.innerHTML = '';
    const sortedGuesses = getSortedGuesses();
    updateSummary(sortedGuesses);

    if (sortedGuesses.length === 0) {
        const emptyLi = document.createElement('li');
        emptyLi.className = 'guess-empty';
        emptyLi.textContent = '아직 입력한 단어가 없습니다.';
        list.appendChild(emptyLi);
        return;
    }

    sortedGuesses.forEach((guess) => {
        const li = document.createElement('li');
        li.className = 'guess-item';
        if (guess.id === latestGuessId) {
            li.classList.add('latest-guess');
        }

        let rankClass = 'rank-cold';
        if (guess.isCorrect) {
            rankClass = 'rank-correct';
        } else if (typeof guess.rank === 'number' && guess.rank <= 1000) {
            rankClass = 'rank-hot';
        }
        li.classList.add(rankClass);

        const wordCol = document.createElement('div');
        wordCol.className = 'word-col';
        wordCol.textContent = guess.word;

        const guessMain = document.createElement('div');
        guessMain.className = 'guess-main';
        guessMain.appendChild(wordCol);

        if (guess.id === latestGuessId) {
            const latestChip = document.createElement('span');
            latestChip.className = 'latest-chip';
            latestChip.textContent = '최근 입력';
            guessMain.appendChild(latestChip);
        }

        const metaCol = document.createElement('div');
        metaCol.className = 'meta-col';
        metaCol.textContent = `${guess.id}번째 입력`;

        const progressBg = document.createElement('div');
        progressBg.className = 'progress-bg';

        const progressFill = document.createElement('div');
        progressFill.className = 'progress-fill';
        const graphWidth = Math.max(0, Math.min(100, Number(guess.score)));
        progressFill.style.width = `${graphWidth}%`;
        progressBg.appendChild(progressFill);

        const scoreCol = document.createElement('div');
        scoreCol.className = 'score-col';
        scoreCol.textContent = Number(guess.score).toFixed(2);

        const rankCol = document.createElement('div');
        rankCol.className = 'rank-col';
        rankCol.textContent = guess.isCorrect ? '정답' : `#${guess.rank}`;

        const statsCol = document.createElement('div');
        statsCol.className = 'stats-col';
        statsCol.appendChild(progressBg);
        statsCol.appendChild(scoreCol);
        statsCol.appendChild(rankCol);

        li.appendChild(guessMain);
        li.appendChild(metaCol);
        li.appendChild(statsCol);
        list.appendChild(li);
    });
}

async function requestHint() {
    if (isGameOver || isBusy) return;

    if (hintStep >= HINT_RANKS.length) {
        setStatus('모든 힌트를 이미 사용했습니다.', true);
        return;
    }

    const nextStep = hintStep + 1;
    setBusy(true);
    setStatus('힌트를 불러오는 중입니다...');

    try {
        const response = await fetch(GAME_CONFIG.hintApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': GAME_CONFIG.csrfToken,
            },
            body: JSON.stringify({ step: nextStep }),
        });

        const data = await response.json();

        if (!response.ok || data.result !== 'success') {
            setStatus(data.message || '힌트를 가져오지 못했습니다.', true);
            return;
        }

        hintStep = nextStep;
        updateHintButtonLabel();

        if (hintArea && hintList) {
            hintArea.style.display = 'block';
            const li = document.createElement('li');
            li.textContent = `${data.rank}위 단어: ${data.word} (유사도 ${Number(data.score).toFixed(2)})`;
            hintList.appendChild(li);
        }

        setStatus(`${hintStep}번째 힌트를 확인했습니다.`);
    } catch (err) {
        console.error(err);
        setStatus('힌트를 가져오지 못했습니다.', true);
    } finally {
        if (!isGameOver) {
            setBusy(false);
        }
    }
}

async function surrenderGame() {
    if (isGameOver || isBusy) return;

    const approved = window.confirm('포기하고 정답을 공개할까요?');
    if (!approved) return;

    setBusy(true);
    setStatus('정답을 확인하는 중입니다...');

    try {
        const response = await fetch(GAME_CONFIG.surrenderApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': GAME_CONFIG.csrfToken,
            },
        });

        const data = await response.json();

        if (!response.ok || data.result !== 'success') {
            setStatus(data.message || '정답 공개에 실패했습니다.', true);
            return;
        }

        setStatus(`정답은 '${data.answer}' 입니다.`);
        finishGame({
            solved: false,
            answer: data.answer,
            similarWords: data.similar_words || [],
        });
    } catch (err) {
        console.error(err);
        setStatus('정답 공개에 실패했습니다.', true);
    } finally {
        if (!isGameOver) {
            setBusy(false);
        }
    }
}

async function shareResult() {
    const today = new Date().toISOString().slice(0, 10);
    const count = guesses.length;
    const link = 'https://monosaccharide180.com/games/kkomantle/';

    let text = `🧩 꼬맨틀 (${today})\n🎉 ${count}번 만에 정답을 찾았습니다!\n\n`;
    text += '(상위 기록)\n';

    getSortedGuesses().slice(0, 5).forEach((guess) => {
        let emoji = '☁️';
        if (guess.isCorrect) emoji = '☀️';
        else if (guess.score >= 40) emoji = '🔥';
        else if (guess.score >= 20) emoji = '💧';

        text += `${emoji} ${Number(guess.score).toFixed(2)}\n`;
    });

    text += `\n게임하러 가기: ${link}`;

    try {
        await navigator.clipboard.writeText(text);
        setStatus('결과가 복사되었습니다.');
        if (window.trackEvent) {
            window.trackEvent('share_result', {
                event_category: 'games',
                event_label: 'kkomantle',
            });
        }
    } catch (err) {
        console.error(err);
        setStatus('복사에 실패했습니다. 수동으로 복사해 주세요.', true);
    }
}

function openHistoryModal() {
    if (!historyModal) return;
    historyModal.classList.remove('hidden');
    loadHistory();
}

function closeHistoryModal() {
    if (!historyModal) return;
    historyModal.classList.add('hidden');
}

function renderHistory(items) {
    if (!historyList) return;
    historyList.innerHTML = '';

    if (!Array.isArray(items) || items.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'guess-empty';
        empty.textContent = '표시할 이전 정답이 없습니다.';
        historyList.appendChild(empty);
        return;
    }

    items.forEach((item) => {
        const card = document.createElement('section');
        card.className = 'history-card';

        const title = document.createElement('h3');
        title.textContent = `${item.date} 정답: ${item.answer}`;
        card.appendChild(title);

        const words = Array.isArray(item.top_words) ? item.top_words : [];
        if (words.length === 0) {
            const noWords = document.createElement('p');
            noWords.className = 'history-meta';
            noWords.textContent = 'Top 단어 정보가 없습니다.';
            card.appendChild(noWords);
            historyList.appendChild(card);
            return;
        }

        const ul = document.createElement('ul');
        ul.className = 'history-top-list';
        words.forEach((wordItem) => {
            const li = document.createElement('li');
            const score = Number(wordItem.score);
            const scoreText = Number.isFinite(score) ? score.toFixed(2) : '-';
            li.textContent = `#${wordItem.rank} ${wordItem.word} (${scoreText})`;
            ul.appendChild(li);
        });
        card.appendChild(ul);
        historyList.appendChild(card);
    });
}

async function loadHistory(days = 7) {
    if (historyLoading || !GAME_CONFIG.historyApiUrl) return;
    historyLoading = true;
    if (historyBtn) historyBtn.disabled = true;
    if (historyMeta) historyMeta.textContent = '불러오는 중...';

    try {
        const url = `${GAME_CONFIG.historyApiUrl}?days=${encodeURIComponent(days)}`;
        const response = await fetch(url);
        const data = await response.json();

        if (!response.ok || data.result !== 'success') {
            setStatus(data.message || '이전 정답 정보를 가져오지 못했습니다.', true);
            if (historyMeta) historyMeta.textContent = '이전 정답 정보를 가져오지 못했습니다.';
            renderHistory([]);
            return;
        }

        renderHistory(data.items || []);
        if (historyMeta) {
            const count = Array.isArray(data.items) ? data.items.length : 0;
            historyMeta.textContent = `${data.start_date}부터 최근 ${count}일`;
        }
    } catch (err) {
        console.error(err);
        if (historyMeta) historyMeta.textContent = '서버 연결에 실패했습니다.';
        renderHistory([]);
    } finally {
        historyLoading = false;
        if (historyBtn) historyBtn.disabled = false;
    }
}

updateHintButtonLabel();
setBusy(false);
renderList();
