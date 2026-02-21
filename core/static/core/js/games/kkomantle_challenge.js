const challengeStatus = document.getElementById('challengeStatus');
const roundLabel = document.getElementById('roundLabel');
const clearLabel = document.getElementById('clearLabel');
const attemptLabel = document.getElementById('attemptLabel');
const roundClearFlash = document.getElementById('roundClearFlash');
const roundClearBanner = document.getElementById('roundClearBanner');
const hintList = document.getElementById('hintList');
const challengeGuessForm = document.getElementById('challengeGuessForm');
const challengeInput = document.getElementById('challengeInput');
const challengeSubmitBtn = document.getElementById('challengeSubmitBtn');
const challengeRestartBtn = document.getElementById('challengeRestartBtn');
const challengeCard = document.querySelector('.challenge-card');
const challengeGuessList = document.getElementById('challengeGuessList');
const challengeResult = document.getElementById('challengeResult');
const resultSummary = document.getElementById('resultSummary');
const resultAnswer = document.getElementById('resultAnswer');
const resultRelated = document.getElementById('resultRelated');
const rankSubmitArea = document.getElementById('rankSubmitArea');
const rankNameInput = document.getElementById('rankNameInput');
const rankSubmitBtn = document.getElementById('rankSubmitBtn');
const challengeRankList = document.getElementById('challengeRankList');

let busy = false;
let gameOver = false;
let solvedRounds = 0;
let attemptUsed = 0;
let attemptLeft = 0;
let roundGuessSet = new Set();
let eligibleScore = null;
let guessSequence = 0;
let roundClearBannerTimer = null;

function setStatus(message, isError = false) {
    if (!challengeStatus) return;
    challengeStatus.textContent = message;
    challengeStatus.style.color = isError ? '#b91c1c' : '#4b5563';
}

function setBusy(nextBusy) {
    busy = nextBusy;
    if (challengeSubmitBtn) challengeSubmitBtn.disabled = nextBusy || gameOver;
    if (challengeInput) challengeInput.disabled = nextBusy || gameOver;
    if (challengeRestartBtn) challengeRestartBtn.disabled = nextBusy;
    if (rankSubmitBtn) rankSubmitBtn.disabled = nextBusy;
}

function updateStats({ round, solved, used, left }) {
    if (roundLabel) roundLabel.textContent = String(round);
    if (clearLabel) clearLabel.textContent = String(solved);
    if (attemptLabel) attemptLabel.textContent = String(left);

    solvedRounds = Number(solved) || 0;
    attemptUsed = Number(used) || 0;
    attemptLeft = Number(left) || 0;
}

function updateHint(hint) {
    if (!hintList) return;
    hintList.innerHTML = '';

    if (!Array.isArray(hint) || hint.length === 0) {
        const li = document.createElement('li');
        li.textContent = '힌트 정보를 불러오지 못했습니다.';
        hintList.appendChild(li);
        return;
    }

    hint.forEach((item) => {
        const li = document.createElement('li');
        const score = Number(item.score);
        const scoreText = Number.isFinite(score) ? score.toFixed(2) : '-';
        li.textContent = `#${item.rank} 단어: ${item.word} (유사도 ${scoreText})`;
        hintList.appendChild(li);
    });
}

function clearRoundGuesses() {
    roundGuessSet = new Set();
    guessSequence = 0;
    if (challengeGuessList) challengeGuessList.innerHTML = '';
}

function playRoundClearEffect({ solved, nextRound, answer }) {
    if (challengeCard) {
        challengeCard.classList.remove('round-clear-hit');
        void challengeCard.offsetWidth;
        challengeCard.classList.add('round-clear-hit');
        setTimeout(() => challengeCard.classList.remove('round-clear-hit'), 760);
    }

    if (roundClearFlash) {
        roundClearFlash.classList.remove('active');
        void roundClearFlash.offsetWidth;
        roundClearFlash.classList.add('active');
        setTimeout(() => roundClearFlash.classList.remove('active'), 620);
    }

    if (roundClearBanner) {
        if (roundClearBannerTimer) clearTimeout(roundClearBannerTimer);
        roundClearBanner.classList.remove('hidden', 'show');
        roundClearBanner.textContent = `라운드 클리어! (${solved}회 성공) '${answer}' 정답, 다음은 Round ${nextRound}`;
        void roundClearBanner.offsetWidth;
        roundClearBanner.classList.add('show');
        roundClearBannerTimer = setTimeout(() => {
            roundClearBanner.classList.add('hidden');
            roundClearBanner.classList.remove('show');
        }, 2200);
    }

    if (navigator.vibrate) {
        navigator.vibrate([40, 24, 70]);
    }
}

function addGuessItem(word, score, rank) {
    if (!challengeGuessList) return;
    guessSequence += 1;
    const li = document.createElement('li');
    li.className = 'guess-item';
    const scoreNum = Number(score);
    const scoreText = Number.isFinite(scoreNum) ? scoreNum.toFixed(2) : '-';
    li.innerHTML = `<strong>${guessSequence}. ${word}</strong><span>유사도 ${scoreText} / 순위 #${rank}</span>`;
    challengeGuessList.prepend(li);
}

function renderRelated(words) {
    if (!resultRelated) return;
    resultRelated.innerHTML = '';
    if (!Array.isArray(words) || words.length === 0) return;
    words.forEach((item) => {
        const li = document.createElement('li');
        const score = Number(item.score);
        const scoreText = Number.isFinite(score) ? score.toFixed(2) : '-';
        li.textContent = `#${item.rank} ${item.word} (${scoreText})`;
        resultRelated.appendChild(li);
    });
}

function renderRanking(rows) {
    if (!challengeRankList) return;
    challengeRankList.innerHTML = '';

    if (!Array.isArray(rows) || rows.length === 0) {
        const li = document.createElement('li');
        li.textContent = '아직 등록된 기록이 없습니다.';
        challengeRankList.appendChild(li);
        return;
    }

    rows.forEach((row, index) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${index + 1}. ${row.name}</span><strong>${row.score} 라운드</strong>`;
        challengeRankList.appendChild(li);
    });
}

async function loadRanking() {
    try {
        const response = await fetch(CHALLENGE_CONFIG.rankApiUrl);
        const data = await response.json();
        if (!response.ok || data.status !== 'success') return;
        renderRanking(data.ranking || []);
    } catch (error) {
        console.error(error);
    }
}

async function startChallenge() {
    if (busy) return;
    setBusy(true);
    setStatus('새 챌린지를 준비하는 중입니다...');

    try {
        const response = await fetch(CHALLENGE_CONFIG.startApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CHALLENGE_CONFIG.csrfToken,
            },
            body: JSON.stringify({ start: true }),
        });
        const data = await response.json();

        if (!response.ok || data.result !== 'success') {
            setStatus(data.message || '챌린지를 시작하지 못했습니다.', true);
            return;
        }

        gameOver = false;
        eligibleScore = null;
        if (challengeResult) challengeResult.classList.add('hidden');
        if (rankSubmitArea) rankSubmitArea.classList.add('hidden');
        clearRoundGuesses();
        updateStats({
            round: data.round,
            solved: data.solved_rounds,
            used: data.attempt_used,
            left: data.attempt_left,
        });
        updateHint(data.hint);
        renderRanking(data.ranking || []);
        if (challengeInput) {
            challengeInput.value = '';
            challengeInput.focus();
        }
        setStatus('챌린지가 시작되었습니다. 10번 안에 정답을 맞춰보세요.');
    } catch (error) {
        console.error(error);
        setStatus('서버 연결에 실패했습니다.', true);
    } finally {
        setBusy(false);
    }
}

function showGameOver(data) {
    gameOver = true;
    eligibleScore = Number(data.eligible_score);
    setBusy(false);

    if (challengeResult) challengeResult.classList.remove('hidden');
    if (resultSummary) resultSummary.textContent = `클리어 라운드: ${data.solved_rounds}`;
    if (resultAnswer) resultAnswer.textContent = `마지막 정답: ${data.answer}`;
    renderRelated(data.similar_words || []);

    if (rankSubmitArea) {
        if (Number.isFinite(eligibleScore)) {
            rankSubmitArea.classList.remove('hidden');
        } else {
            rankSubmitArea.classList.add('hidden');
        }
    }

    if (challengeInput) challengeInput.disabled = true;
    if (challengeSubmitBtn) challengeSubmitBtn.disabled = true;
    setStatus('실패했습니다. 기록을 랭킹에 등록할 수 있습니다.');
}

async function submitGuess() {
    if (busy || gameOver) return;
    const word = (challengeInput.value || '').trim();
    if (!word) return;

    if (roundGuessSet.has(word)) {
        setStatus('이번 라운드에서 이미 입력한 단어입니다.', true);
        challengeInput.value = '';
        return;
    }

    setBusy(true);
    setStatus('단어를 확인하는 중입니다...');

    try {
        const response = await fetch(CHALLENGE_CONFIG.guessApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CHALLENGE_CONFIG.csrfToken,
            },
            body: JSON.stringify({ word }),
        });
        const data = await response.json();

        if (!response.ok || data.result === 'error' || data.result === 'fail') {
            setStatus(data.message || '처리에 실패했습니다.', true);
            return;
        }

        roundGuessSet.add(word);
        addGuessItem(word, data.score, data.rank);

        if (data.result === 'success') {
            updateStats({
                round: data.round,
                solved: data.solved_rounds,
                used: data.attempt_used,
                left: data.attempt_left,
            });
            setStatus('계속 시도해보세요.');
            return;
        }

        if (data.result === 'round_clear') {
            updateStats({
                round: data.next_round,
                solved: data.solved_rounds,
                used: data.attempt_used,
                left: data.attempt_left,
            });
            clearRoundGuesses();
            updateHint(data.hint);
            playRoundClearEffect({
                solved: data.solved_rounds,
                nextRound: data.next_round,
                answer: data.answer,
            });
            setStatus(`라운드 클리어! 다음 라운드(${data.next_round}) 시작.`);
            return;
        }

        if (data.result === 'game_over') {
            showGameOver(data);
            return;
        }

        setStatus('알 수 없는 응답입니다.', true);
    } catch (error) {
        console.error(error);
        setStatus('서버 연결에 실패했습니다.', true);
    } finally {
        if (!gameOver) {
            setBusy(false);
            if (challengeInput) {
                challengeInput.value = '';
                challengeInput.focus();
            }
        }
    }
}

async function submitRank() {
    if (!Number.isFinite(eligibleScore) || eligibleScore < 0) {
        setStatus('등록 가능한 점수가 없습니다.', true);
        return;
    }

    const playerName = (rankNameInput.value || '').trim();
    if (!playerName) {
        setStatus('닉네임을 입력해주세요.', true);
        return;
    }

    setBusy(true);
    setStatus('랭킹 등록 중입니다...');

    try {
        const response = await fetch(CHALLENGE_CONFIG.rankApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CHALLENGE_CONFIG.csrfToken,
            },
            body: JSON.stringify({
                player_name: playerName,
                score: eligibleScore,
            }),
        });
        const data = await response.json();

        if (!response.ok || data.status !== 'success') {
            setStatus(data.message || '랭킹 등록에 실패했습니다.', true);
            return;
        }

        if (rankSubmitArea) rankSubmitArea.classList.add('hidden');
        renderRanking(data.ranking || []);
        setStatus('랭킹에 등록되었습니다.');
    } catch (error) {
        console.error(error);
        setStatus('랭킹 등록에 실패했습니다.', true);
    } finally {
        setBusy(false);
    }
}

if (challengeGuessForm) {
    challengeGuessForm.addEventListener('submit', (event) => {
        event.preventDefault();
        submitGuess();
    });
}

if (challengeRestartBtn) {
    challengeRestartBtn.addEventListener('click', () => {
        startChallenge();
    });
}

if (rankSubmitBtn) {
    rankSubmitBtn.addEventListener('click', submitRank);
}

loadRanking();
startChallenge();
