let state = 'waiting'; // waiting, ready, now
let startTime;
let timeoutId;

// 3판 평균을 위한 변수들
let currentRound = 1;
const maxRounds = 3;
let roundScores = []; 

const area = document.getElementById('click-area');
const icon = document.getElementById('status-icon');
const mainText = document.getElementById('status-text');
const subText = document.getElementById('sub-text');
const attemptEl = document.getElementById('current-attempt');

document.addEventListener('DOMContentLoaded', () => {
    loadRanking();
    
    area.addEventListener('mousedown', handleClick);
    area.addEventListener('touchstart', (e) => { e.preventDefault(); handleClick(); });
});

function handleClick() {
    if (state === 'waiting') {
        // 게임 시작 (빨강 화면)
        setState('ready');
        const randomTime = Math.floor(Math.random() * 3000) + 2000;
        
        timeoutId = setTimeout(() => {
            setState('now');
            startTime = new Date().getTime();
        }, randomTime);
        
    } else if (state === 'ready') {
        // 부정 출발 (빨강일 때 클릭)
        clearTimeout(timeoutId);
        setState('waiting'); // 다시 대기 상태로
        mainText.innerText = "너무 빨라요! 😅";
        subText.innerText = "초록색이 되면 클릭하세요. (터치해서 재시도)";
        area.style.backgroundColor = "#ffcc00"; 
        
    } else if (state === 'now') {
        // 성공 (초록일 때 클릭)
        const endTime = new Date().getTime();
        const score = endTime - startTime;
        
        // 기록 저장
        roundScores.push(score);
        
        if (currentRound < maxRounds) {
            // 아직 라운드가 남았을 때
            currentRound++;
            attemptEl.innerText = currentRound; // 상단 숫자 변경
            setState('waiting');
            // 문구 변경 (다음 라운드 안내)
            mainText.innerText = `${score}ms!`;
            subText.innerText = "터치해서 다음 라운드 시작";
        } else {
            // 3판 모두 종료 -> 결과 계산
            finishGame();
        }
    }
}

function setState(newState) {
    state = newState;
    area.className = `click-area state-${newState}`;
    
    if (newState === 'waiting') {
        icon.innerText = '⚡';
        // 첫 시작인지, 중간 단계인지에 따라 문구 다르게
        if (roundScores.length === 0 && currentRound === 1) {
            mainText.innerText = "화면을 클릭해서 시작";
            subText.innerText = "3회 평균을 측정합니다.";
        } 
        // (중간 문구는 handleClick에서 처리함)
    } else if (newState === 'ready') {
        icon.innerText = '✋';
        mainText.innerText = "기다리세요...";
        subText.innerText = "집중하세요!";
    } else if (newState === 'now') {
        icon.innerText = '💥';
        mainText.innerText = "클릭!!!";
        subText.innerText = "지금입니다!";
    }
}

// === 결과 처리 및 랭킹 ===
let finalAverage = 0;

function finishGame() {
    // 평균 계산 (정수 반올림)
    const sum = roundScores.reduce((a, b) => a + b, 0);
    finalAverage = Math.round(sum / maxRounds);
    
    // 모달 표시
    document.getElementById('final-score').innerText = finalAverage;
    document.getElementById('detail-log').innerText = 
        `1차: ${roundScores[0]}ms | 2차: ${roundScores[1]}ms | 3차: ${roundScores[2]}ms`;
    
    document.getElementById('result-modal').classList.remove('hidden');
    setState('waiting'); // 배경 초기화
}

function closeModal() {
    document.getElementById('result-modal').classList.add('hidden');
    // 게임 완전 초기화
    currentRound = 1;
    roundScores = [];
    attemptEl.innerText = 1;
    
    // 화면 문구 원상복구
    icon.innerText = '⚡';
    mainText.innerText = "다시 도전?";
    subText.innerText = "화면을 클릭해서 시작";
}

function submitScore() {
    const name = document.getElementById('player-name').value;
    if (!name) return alert("이름을 입력해주세요.");
    
    if (!window.gameConfig) return alert("설정 오류");

    fetch(window.gameConfig.apiEndpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": window.gameConfig.csrfToken
        },
        body: JSON.stringify({ player_name: name, score: finalAverage }) // 평균값 전송
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            loadRanking();
            closeModal();
        } else {
            alert("오류: " + data.message);
        }
    });
}

function loadRanking() {
    if (!window.gameConfig) return;

    fetch(window.gameConfig.apiEndpoint)
    .then(res => res.json())
    .then(data => {
        const list = document.getElementById('rank-list');
        list.innerHTML = '';
        if(data.ranking.length === 0) {
            list.innerHTML = '<li style="justify-content:center; color:#999;">기록이 없습니다.</li>';
            return;
        }
        data.ranking.forEach((r, idx) => {
            let badge = '';
            if(idx === 0) badge = '🥇';
            else if(idx === 1) badge = '🥈';
            else if(idx === 2) badge = '🥉';
            
            list.innerHTML += `
                <li>
                    <span><span class="rank-num">${idx+1}</span> ${badge} ${r.name}</span>
                    <span style="font-weight:bold; color:#1d1d1f;">${r.score}ms</span>
                </li>`;
        });
    });
}