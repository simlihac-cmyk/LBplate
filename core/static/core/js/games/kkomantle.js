// 전역 변수 설정
const input = document.getElementById('wordInput');
const list = document.getElementById('guessList');
const submitBtn = document.getElementById('submitBtn');
const successArea = document.getElementById('successArea');
const statusText = document.getElementById('statusText');

let guesses = []; // 추측 기록 저장
let isGameOver = false;

// 엔터키 입력 리스너
input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !isGameOver) submitGuess();
});

// 추측 제출 함수
function submitGuess() {
    if (isGameOver) return;
    
    const word = input.value.trim();
    if (!word) return;

    // 중복 체크
    if (guesses.some(g => g.word === word)) {
        alert("이미 입력한 단어입니다!");
        input.value = '';
        return;
    }

    // 로딩 표시
    submitBtn.disabled = true;
    submitBtn.innerText = "...";

    // 서버로 전송 (HTML에서 넘겨받은 GAME_CONFIG 사용)
    fetch(GAME_CONFIG.apiUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": GAME_CONFIG.csrfToken 
        },
        body: JSON.stringify({ word: word })
    })
    .then(res => res.json())
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.innerText = "추측하기";

        if (data.result === 'fail' || data.result === 'error') {
            alert(data.message);
        } else {
            // 성공하면 리스트에 추가
            addGuess(word, data.score, data.rank, data.result === 'correct');
        }
        input.value = '';
        input.focus();
    })
    .catch(err => {
        submitBtn.disabled = false;
        submitBtn.innerText = "추측하기";
        console.error(err);
        alert("서버 연결에 실패했습니다.");
    });
}

// 화면에 리스트 추가 함수
function addGuess(word, score, rank, isCorrect) {
    // 기록 추가
    guesses.push({ word, score, rank, isCorrect });
    
    // 정답일 경우 게임 종료 처리
    if (isCorrect) {
        isGameOver = true;
        statusText.innerText = "오늘의 단어를 찾았습니다!";
        input.disabled = true;
        submitBtn.disabled = true;
        
        // 성공 모달 보여주기
        successArea.style.display = 'block';
        document.getElementById('finalCount').innerText = guesses.length;
    }

    // 점수 높은 순으로 정렬 (정답이 항상 맨 위로 오게)
    guesses.sort((a, b) => b.score - a.score);
    
    renderList();
}

// 리스트 렌더링 함수
function renderList() {
    list.innerHTML = ''; // 싹 지우고 다시 그리기
    
    guesses.forEach(g => {
        const li = document.createElement('li');
        
        let rankClass = 'rank-cold';
        let rankText = g.rank;

        // 스타일 결정
        if (g.isCorrect) {
            rankClass = 'rank-correct';
            rankText = '🎉 정답';
        }
        else if (typeof g.rank === 'number' && g.rank <= 1000) rankClass = 'rank-hot';
        
        // 점수가 음수면 0으로 처리 (그래프용)
        const graphWidth = Math.max(0, g.score);

        li.className = `guess-item ${rankClass}`;
        li.innerHTML = `
            <div class="word-col">${g.word}</div>
            <div class="progress-bg">
                <div class="progress-fill" style="width: ${graphWidth}%"></div>
            </div>
            <div class="score-col">${g.score.toFixed(2)}</div>
            <div class="rank-col">#${rankText}</div>
        `;
        list.appendChild(li);
    });
}

// 공유하기 기능 (스포일러 방지 버전)
function shareResult() {
    const today = new Date().toISOString().slice(0, 10); // 날짜
    const count = guesses.length; // 시도 횟수
    const link = "https://monosaccharide180.com/games/kkomantle/";

    // 1. 기본 문구
    let text = `🧩 꼬맨틀 (${today})\n🎉 ${count}번 만에 정답을 찾았습니다!\n\n`;

    // 2. 단어는 숨기고 '점수(유사도)'만 보여주기
    text += "(상위 기록)\n";
    guesses.slice(0, 5).forEach(g => {
        let emoji = '☁️';
        if (g.isCorrect) emoji = '☀️';       // 정답
        else if (g.score >= 40) emoji = '🔥'; // 뜨거움
        else if (g.score >= 20) emoji = '💧'; // 미지근함
        
        // 단어(g.word)는 빼고 점수만 넣습니다!
        text += `${emoji} ${g.score.toFixed(2)}\n`; 
    });

    // 3. 게임하러 가기 링크
    text += `\n게임하러 가기: ${link}`;

    // 클립보드 복사
    navigator.clipboard.writeText(text).then(() => {
        alert("결과가 복사되었습니다! 친구들에게 공유해보세요. 📋");
    }).catch(err => {
        alert("복사에 실패했습니다. :(");
    });
}