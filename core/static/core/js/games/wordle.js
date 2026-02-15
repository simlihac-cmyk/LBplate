// === 1. 단어 리스트 및 초기화 ===
const WORDS = [
    "APPLE", "BEACH", "BRAIN", "BREAD", "BRUSH", "CHAIR", "CHEST", "CHORD", "CLICK", "CLOCK",
    "CLOUD", "DANCE", "DIARY", "DRINK", "DRIVE", "EARTH", "FEAST", "FIELD", "FRUIT", "GLASS",
    "GRAPE", "GREEN", "GHOST", "HEART", "HOUSE", "IMAGE", "JUICE", "LIGHT", "LEMON", "MELON",
    "MONEY", "MUSIC", "NIGHT", "OCEAN", "PARTY", "PHONE", "PIANO", "PILOT", "PIZZA", "PLANE",
    "PLANT", "PLATE", "POWER", "RADIO", "RIVER", "ROBOT", "SHIRT", "SHOES", "SMILE", "SNAKE",
    "SPACE", "SPOON", "STORM", "TABLE", "TIGER", "TOAST", "TOUCH", "TRAIN", "TRUCK", "VOICE",
    "WATCH", "WATER", "WHALE", "WORLD", "WRITE", "YOUTH", "ZEBRA", "ALARM", "ANGRY", "BAKER",
    "BIRTH", "BLOCK", "BLOOD", "BOARD", "BRAVE", "BROWN", "CANDY", "CAUSE", "CHAIN", "CLEAN",
    "CLASS", "COUNT", "CREAM", "CROSS", "CROWN", "CYCLE", "DAILY", "DREAM", "DRESS", "DRIVE"
];

let secretWord = "";
let currentRow = 0;
let currentTile = 0;
const rows = 6;
const cols = 5;
let isGameOver = false;
let guesses = [];

document.addEventListener('DOMContentLoaded', () => {
    initGame();
    loadRanking();
    
    // 키보드 입력
    document.addEventListener('keydown', handlePhysicalKeyboard);

    const submitBtn = document.getElementById('btn-submit');
    if (submitBtn) submitBtn.addEventListener('click', submitScore);

    const closeModalBtn = document.getElementById('close-modal-btn');
    if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
});

function initGame() {
    // 랜덤 단어 선택 및 공백 제거 (안전장치)
    secretWord = WORDS[Math.floor(Math.random() * WORDS.length)].trim().toUpperCase();
    
    // 변수 초기화
    currentRow = 0;
    currentTile = 0;
    isGameOver = false;
    guesses = Array(6).fill().map(() => Array(5).fill(""));
    
    createBoard();
    createKeyboard();
    
    // 모달 확실히 닫기
    const modal = document.getElementById('result-modal');
    if(modal) modal.classList.add('hidden');
}

function createBoard() {
    const board = document.getElementById('board');
    board.innerHTML = '';
    
    for (let r = 0; r < rows; r++) {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'row';
        for (let c = 0; c < cols; c++) {
            const tile = document.createElement('div');
            tile.className = 'tile';
            tile.id = `tile-${r}-${c}`;
            rowDiv.appendChild(tile);
        }
        board.appendChild(rowDiv);
    }
}

function createKeyboard() {
    const keyboard = document.getElementById('keyboard');
    keyboard.innerHTML = '';
    
    const keys = [
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
        ["ENTER", "Z", "X", "C", "V", "B", "N", "M", "BACK"]
    ];
    
    keys.forEach(row => {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'key-row';
        row.forEach(key => {
            const keyDiv = document.createElement('div');
            keyDiv.textContent = key === "BACK" ? "⌫" : key;
            keyDiv.className = key.length > 1 ? 'key wide' : 'key';
            keyDiv.id = `key-${key}`;
            keyDiv.addEventListener('click', () => handleKey(key));
            rowDiv.appendChild(keyDiv);
        });
        keyboard.appendChild(rowDiv);
    });
}

function handlePhysicalKeyboard(e) {
    if (isGameOver) return;
    
    const key = e.key.toUpperCase();
    if (key === "ENTER") handleKey("ENTER");
    else if (key === "BACKSPACE") handleKey("BACK");
    else if (/^[A-Z]$/.test(key)) handleKey(key);
}

function handleKey(key) {
    if (isGameOver) return;

    if (key === "ENTER") {
        if (currentTile === 5) checkGuess();
    } else if (key === "BACK") {
        if (currentTile > 0) {
            currentTile--;
            guesses[currentRow][currentTile] = "";
            const tile = document.getElementById(`tile-${currentRow}-${currentTile}`);
            if(tile) {
                tile.textContent = "";
                tile.removeAttribute("data-state");
            }
        }
    } else {
        if (currentTile < 5) {
            guesses[currentRow][currentTile] = key;
            const tile = document.getElementById(`tile-${currentRow}-${currentTile}`);
            if(tile) {
                tile.textContent = key;
                tile.setAttribute("data-state", "active");
            }
            currentTile++;
        }
    }
}

// === ★ 수정된 정답 확인 로직 (디버깅 강화) ===
function checkGuess() {
    const guess = guesses[currentRow].join("").trim().toUpperCase(); // 공백제거 및 대문자화
    
    const rowTiles = [];
    let checkSecret = secretWord.split("");
    
    // 1. 타일 수집 및 초록색(Correct) 확인
    for (let i = 0; i < 5; i++) {
        const tile = document.getElementById(`tile-${currentRow}-${i}`);
        const letter = guesses[currentRow][i];
        
        // 타일 데이터 저장
        rowTiles.push({ tile, letter, state: "absent" }); 

        if (letter === checkSecret[i]) {
            rowTiles[i].state = "correct";
            checkSecret[i] = null;
        }
    }

    // 2. 노란색(Present) 확인
    for (let i = 0; i < 5; i++) {
        if (rowTiles[i].state === "correct") continue;
        const letter = rowTiles[i].letter;
        const indexInSecret = checkSecret.indexOf(letter);
        if (indexInSecret !== -1) {
            rowTiles[i].state = "present";
            checkSecret[indexInSecret] = null;
        }
    }

    // 3. 색상 적용 애니메이션
    rowTiles.forEach((item, index) => {
        setTimeout(() => {
            if(item.tile) item.tile.setAttribute("data-state", item.state);
            updateKeyboardColor(item.letter, item.state);
        }, index * 100); 
    });

    // 4. 결과 판정 (시간차 실행)
    setTimeout(() => {
        if (guess === secretWord) {
            isGameOver = true;
            showModal(true);
        } else {
            if (currentRow >= 5) {
                isGameOver = true;
                showModal(false);
            } else {
                currentRow++;
                currentTile = 0;
            }
        }
    }, 600); // 애니메이션 시간 고려
}

function updateKeyboardColor(letter, state) {
    const key = document.getElementById(`key-${letter}`);
    if (!key) return;
    
    const currentState = key.getAttribute("data-state");
    if (state === "correct") {
        key.setAttribute("data-state", "correct");
    } else if (state === "present" && currentState !== "correct") {
        key.setAttribute("data-state", "present");
    } else if (state === "absent" && currentState !== "correct" && currentState !== "present") {
        key.setAttribute("data-state", "absent");
    }
}

// === ★ 수정된 모달 표시 (ID 체크 강화) ===
function showModal(success) {
    const modal = document.getElementById('result-modal');
    
    // 모달이 없는 경우 에러 방지
    if (!modal) {
        console.error("Critical Error: Modal element 'result-modal' not found!");
        alert(success ? "Success! (Modal Error)" : "Game Over (Modal Error)");
        return;
    }

    const title = document.getElementById('result-title');
    const msg = document.querySelector('.result-msg');
    const scoreText = document.getElementById('result-score');
    const btnSubmit = document.getElementById('btn-submit');
    const answerWordEl = document.getElementById('answer-word');
    
    if(answerWordEl) answerWordEl.innerText = secretWord;
    
    if (success) {
        if(title) title.innerText = "Fantastic!";
        if(msg) msg.style.display = "none";
        if(scoreText) scoreText.innerHTML = `Attempts: <span id="final-score">${currentRow + 1}</span> / 6`;
        if(btnSubmit) btnSubmit.style.display = "inline-block";
    } else {
        if(title) title.innerText = "Game Over";
        if(msg) msg.style.display = "block";
        if(scoreText) scoreText.innerText = "Failed";
        if(btnSubmit) btnSubmit.style.display = "none";
    }
    
    modal.classList.remove('hidden'); // display: block 처리

    if (window.trackEvent) {
        window.trackEvent('game_finish', {
            event_category: 'games',
            event_label: 'wordle',
            result: success ? 'success' : 'fail',
            attempts: currentRow + 1,
        });
    }
}

function closeModal() {
    const modal = document.getElementById('result-modal');
    if(modal) modal.classList.add('hidden');
    initGame();
    // 키보드 색상 초기화
    document.querySelectorAll('.key').forEach(k => k.removeAttribute('data-state'));
}

function submitScore() {
    const nameInput = document.getElementById('player-name');
    const name = nameInput ? nameInput.value : "Anonymous";
    
    if (!name) return alert("Please enter your name.");
    if (!window.gameConfig) return;

    fetch(window.gameConfig.apiEndpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": window.gameConfig.csrfToken
        },
        body: JSON.stringify({ 
            player_name: name, 
            score: currentRow + 1 
        }) 
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            if (window.trackEvent) {
                window.trackEvent('ranking_submit', {
                    event_category: 'games',
                    event_label: 'wordle',
                    score: currentRow + 1,
                });
            }
            loadRanking();
            closeModal();
        } else {
            alert("Error: " + data.message);
        }
    });
}

function loadRanking() {
    if (!window.gameConfig) return;

    fetch(window.gameConfig.apiEndpoint)
    .then(res => res.json())
    .then(data => {
        const list = document.getElementById('rank-list');
        if(!list) return;

        list.innerHTML = '';
        if(data.ranking.length === 0) {
            list.innerHTML = '<li style="justify-content:center; color:#999;">Be the first winner!</li>';
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
                    <span style="font-weight:bold; color:#1d1d1f;">${r.score} tries</span>
                </li>`;
        });
    });
}
