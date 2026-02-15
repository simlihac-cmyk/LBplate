// === 1. 게임 변수 및 초기화 ===
const boardSize = 4;
let grid = [];
let score = 0;
let startX, startY; // 터치 좌표 저장용
let currentRankPeriod = 'daily';

document.addEventListener('DOMContentLoaded', () => {
    initGame();
    bindRankPeriodToggle();
    loadRanking(currentRankPeriod);
    
    // 키보드 이벤트
    document.addEventListener('keydown', handleInput);
    
    // 터치 이벤트 (모바일)
    const boardEl = document.getElementById('game-board');
    if(boardEl) {
        boardEl.addEventListener('touchstart', handleTouchStart, {passive: false});
        boardEl.addEventListener('touchend', handleTouchEnd, {passive: false});
    }

    const restartBtn = document.getElementById('restart-btn');
    if (restartBtn) restartBtn.addEventListener('click', initGame);

    const submitScoreBtn = document.getElementById('submit-score-btn');
    if (submitScoreBtn) submitScoreBtn.addEventListener('click', submitScore);

    const closeModalBtn = document.getElementById('close-modal-btn');
    if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
});

function bindRankPeriodToggle() {
    const periodButtons = document.querySelectorAll('#rank-period-toggle .period-btn');
    if (!periodButtons.length) return;

    periodButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const selectedPeriod = button.dataset.period;
            if (!selectedPeriod || selectedPeriod === currentRankPeriod) return;

            currentRankPeriod = selectedPeriod;
            updateRankPeriodUI();
            loadRanking(currentRankPeriod);

            if (window.trackEvent) {
                window.trackEvent('rank_period_change', {
                    event_category: 'games',
                    event_label: '2048',
                    period: currentRankPeriod,
                });
            }
        });
    });
}

function updateRankPeriodUI() {
    const title = document.getElementById('rank-title');
    if (title) {
        title.textContent = currentRankPeriod === 'weekly' ? "🏆 Weekly Top 10" : "🏆 Today's Top 10";
    }

    const periodButtons = document.querySelectorAll('#rank-period-toggle .period-btn');
    periodButtons.forEach((button) => {
        button.classList.toggle('active', button.dataset.period === currentRankPeriod);
    });
}

// === 2. 게임 시작 및 그리기 ===
function initGame() {
    grid = Array(boardSize).fill().map(() => Array(boardSize).fill(0));
    score = 0;
    updateScore(0);
    
    const scoreEl = document.getElementById('score');
    if(scoreEl) scoreEl.innerText = '0';
    
    addNewTile();
    addNewTile();
    drawBoard();
}

function drawBoard() {
    const boardEl = document.getElementById('game-board');
    if(!boardEl) return;
    boardEl.innerHTML = '';
    
    for (let r = 0; r < boardSize; r++) {
        for (let c = 0; c < boardSize; c++) {
            const val = grid[r][c];
            const tile = document.createElement('div');
            // 2048 이상의 숫자는 tile-super 클래스로 통일
            const colorClass = val > 2048 ? 'tile-super' : `tile-${val}`;
            tile.className = `tile ${colorClass}`;
            tile.textContent = val > 0 ? val : '';
            boardEl.appendChild(tile);
        }
    }
}

function addNewTile() {
    const emptyCells = [];
    for (let r = 0; r < boardSize; r++) {
        for (let c = 0; c < boardSize; c++) {
            if (grid[r][c] === 0) emptyCells.push({r, c});
        }
    }
    if (emptyCells.length > 0) {
        const {r, c} = emptyCells[Math.floor(Math.random() * emptyCells.length)];
        grid[r][c] = Math.random() < 0.9 ? 2 : 4;
    }
}

// === 3. 입력 처리 ===
function handleInput(e) {
    if(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) {
        e.preventDefault(); 
        move(e.key.replace("Arrow", "").toLowerCase());
    }
}

function handleTouchStart(e) {
    e.preventDefault();
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
}

function handleTouchEnd(e) {
    if (!startX || !startY) return;
    let endX = e.changedTouches[0].clientX;
    let endY = e.changedTouches[0].clientY;
    let diffX = endX - startX;
    let diffY = endY - startY;
    
    if (Math.abs(diffX) < 30 && Math.abs(diffY) < 30) return; // 너무 짧은 터치 무시
    
    if (Math.abs(diffX) > Math.abs(diffY)) {
        move(diffX > 0 ? 'right' : 'left');
    } else {
        move(diffY > 0 ? 'down' : 'up');
    }
    startX = null; startY = null;
}

// === 4. 핵심 이동 로직 (Slide & Merge) ===
function move(direction) {
    let newGrid = JSON.parse(JSON.stringify(grid)); // 깊은 복사

    // 로직 단순화를 위해 모든 방향을 '왼쪽' 기준으로 회전시켜 처리하고 다시 돌림
    if (direction === 'right') newGrid = newGrid.map(row => row.reverse());
    if (direction === 'up') newGrid = transpose(newGrid);
    if (direction === 'down') newGrid = transpose(newGrid).map(row => row.reverse());

    // 합치기 (Slide Logic)
    let moved = false;
    newGrid.forEach(row => {
        let nums = row.filter(val => val !== 0);
        
        for (let i = 0; i < nums.length - 1; i++) {
            if (nums[i] === nums[i+1]) {
                nums[i] *= 2;
                updateScore(nums[i]);
                nums[i+1] = 0;
            }
        }
        
        nums = nums.filter(val => val !== 0);
        while (nums.length < boardSize) {
            nums.push(0);
        }
        
        for(let i=0; i<boardSize; i++) row[i] = nums[i];
    });

    if (direction === 'right') newGrid = newGrid.map(row => row.reverse());
    if (direction === 'up') newGrid = transpose(newGrid);
    if (direction === 'down') newGrid = transpose(newGrid.map(row => row.reverse()));

    if (JSON.stringify(grid) !== JSON.stringify(newGrid)) {
        grid = newGrid;
        addNewTile();
        drawBoard();
        
        setTimeout(() => {
            if (checkGameOver()) showGameOver();
        }, 300);
    }
}

function transpose(matrix) {
    return matrix[0].map((col, i) => matrix.map(row => row[i]));
}

function updateScore(add) {
    score += add;
    const scoreEl = document.getElementById('score');
    if(scoreEl) scoreEl.innerText = score;
    
    const best = localStorage.getItem('2048-best') || 0;
    const bestEl = document.getElementById('best-score');
    
    if (score > best) {
        localStorage.setItem('2048-best', score);
        if(bestEl) bestEl.innerText = score;
    } else {
        if(bestEl) bestEl.innerText = best;
    }
}

// === 5. 게임 오버 체크 ===
function checkGameOver() {
    for (let r=0; r<boardSize; r++) {
        for (let c=0; c<boardSize; c++) {
            if (grid[r][c] === 0) return false;
        }
    }
    for (let r=0; r<boardSize; r++) {
        for (let c=0; c<boardSize; c++) {
            const current = grid[r][c];
            if (c < boardSize - 1 && current === grid[r][c+1]) return false;
            if (r < boardSize - 1 && current === grid[r+1][c]) return false;
        }
    }
    return true;
}

// === 6. UI 및 랭킹 (Django 연동) ===
function showGameOver() {
    document.getElementById('final-score').innerText = score;
    document.getElementById('game-over-modal').classList.remove('hidden');
    if (window.trackEvent) {
        window.trackEvent('game_finish', {
            event_category: 'games',
            event_label: '2048',
            score: score,
        });
    }
}

function closeModal() {
    document.getElementById('game-over-modal').classList.add('hidden');
    initGame();
}

function submitScore() {
    const name = document.getElementById('player-name').value;
    if (!name) return alert("이름을 입력해주세요.");
    
    // HTML에서 선언한 window.gameConfig 사용
    if (!window.gameConfig) return alert("설정 오류: 새로고침 해주세요.");

    fetch(window.gameConfig.apiEndpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": window.gameConfig.csrfToken
        },
        body: JSON.stringify({ player_name: name, score: score })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            if (window.trackEvent) {
                window.trackEvent('ranking_submit', {
                    event_category: 'games',
                    event_label: '2048',
                    score: score,
                });
            }
            loadRanking(currentRankPeriod);
            closeModal();
        } else {
            alert("오류: " + data.message);
        }
    })
    .catch(err => alert("서버 통신 오류"));
}

function loadRanking(period = 'daily') {
    currentRankPeriod = period === 'weekly' ? 'weekly' : 'daily';
    updateRankPeriodUI();

    const bestEl = document.getElementById('best-score');
    if(bestEl) bestEl.innerText = localStorage.getItem('2048-best') || 0;

    if (!window.gameConfig) return;

    const rankUrl = `${window.gameConfig.apiEndpoint}?period=${encodeURIComponent(currentRankPeriod)}`;
    fetch(rankUrl)
    .then(res => res.json())
    .then(data => {
        const list = document.getElementById('rank-list');
        if(!list) return;
        
        list.innerHTML = '';
        if(data.ranking.length === 0) {
            const emptyText = currentRankPeriod === 'weekly'
                ? '이번 주 첫 도전자가 되어보세요!'
                : '오늘의 첫 도전자가 되어보세요!';
            list.innerHTML = `<li style="justify-content:center; color:#999;">${emptyText}</li>`;
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
                    <span style="font-weight:bold; color:var(--text-main);">${r.score}</span>
                </li>`;
        });
    });
}
