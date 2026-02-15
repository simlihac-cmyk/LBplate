const input = document.getElementById('wordInput');
const list = document.getElementById('guessList');
const submitBtn = document.getElementById('submitBtn');
const successArea = document.getElementById('successArea');
const statusText = document.getElementById('statusText');
const guessForm = document.getElementById('guessForm');
const shareBtn = document.getElementById('shareBtn');

let guesses = [];
let isGameOver = false;

function setStatus(message, isError = false) {
    if (!statusText) return;
    statusText.innerText = message;
    statusText.style.color = isError ? '#d93025' : '#666';
}

function setSubmitting(isSubmitting) {
    submitBtn.disabled = isSubmitting || isGameOver;
    submitBtn.innerText = isSubmitting ? '...' : '추측하기';
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

async function submitGuess() {
    if (isGameOver) return;

    const word = input.value.trim();
    if (!word) return;

    if (guesses.some((g) => g.word === word)) {
        setStatus('이미 입력한 단어입니다.', true);
        input.value = '';
        return;
    }

    setSubmitting(true);
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
        setSubmitting(false);

        if (!response.ok || data.result === 'fail' || data.result === 'error') {
            setStatus(data.message || '처리 중 오류가 발생했습니다.', true);
        } else {
            addGuess(word, data.score, data.rank, data.result === 'correct');
            setStatus('좋아요! 다음 단어도 시도해보세요.');
        }

        input.value = '';
        input.focus();
    } catch (err) {
        console.error(err);
        setSubmitting(false);
        setStatus('서버 연결에 실패했습니다.', true);
    }
}

function addGuess(word, score, rank, isCorrect) {
    guesses.push({ word, score, rank, isCorrect });

    if (isCorrect) {
        isGameOver = true;
        setStatus('오늘의 단어를 찾았습니다!');
        input.disabled = true;
        submitBtn.disabled = true;

        successArea.style.display = 'block';
        document.getElementById('finalCount').innerText = guesses.length;

        if (window.trackEvent) {
            window.trackEvent('game_finish', {
                event_category: 'games',
                event_label: 'kkomantle',
                attempts: guesses.length,
            });
        }
    }

    guesses.sort((a, b) => b.score - a.score);
    renderList();
}

function renderList() {
    list.innerHTML = '';

    guesses.forEach((guess) => {
        const li = document.createElement('li');
        li.className = 'guess-item';

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

        const progressBg = document.createElement('div');
        progressBg.className = 'progress-bg';

        const progressFill = document.createElement('div');
        progressFill.className = 'progress-fill';
        const graphWidth = Math.max(0, Math.min(100, guess.score));
        progressFill.style.width = `${graphWidth}%`;
        progressBg.appendChild(progressFill);

        const scoreCol = document.createElement('div');
        scoreCol.className = 'score-col';
        scoreCol.textContent = Number(guess.score).toFixed(2);

        const rankCol = document.createElement('div');
        rankCol.className = 'rank-col';
        rankCol.textContent = guess.isCorrect ? '정답' : `#${guess.rank}`;

        li.appendChild(wordCol);
        li.appendChild(progressBg);
        li.appendChild(scoreCol);
        li.appendChild(rankCol);
        list.appendChild(li);
    });
}

async function shareResult() {
    const today = new Date().toISOString().slice(0, 10);
    const count = guesses.length;
    const link = 'https://monosaccharide180.com/games/kkomantle/';

    let text = `🧩 꼬맨틀 (${today})\n🎉 ${count}번 만에 정답을 찾았습니다!\n\n`;
    text += '(상위 기록)\n';

    guesses.slice(0, 5).forEach((guess) => {
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
