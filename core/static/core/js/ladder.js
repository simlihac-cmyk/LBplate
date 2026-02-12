document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('ladderCanvas');
    const ctx = canvas.getContext('2d');
    
    const btnConfirm = document.getElementById('btnConfirm');
    const btnGenerate = document.getElementById('btnGenerate');
    const btnStart = document.getElementById('btnStart');

    // Canvas 해상도 조정 (선명하게)
    function resizeCanvas() {
        const parent = canvas.parentElement;
        canvas.width = parent.offsetWidth;
        canvas.height = 500;
    }
    
    // 초기화 및 리사이즈 이벤트
    resizeCanvas();
    window.addEventListener('resize', () => { 
        if(!btnStart.disabled && btnGenerate.disabled) resizeCanvas(); // 게임 진행중이 아닐때만
    });

    let game = {
        players: 0,
        width: 0,
        height: 500,
        bridges: [],
        step: 0,
        paddingX: 50,
        // 밝은 테마에 어울리는 선명한 컬러 팔레트
        colors: [
            '#ff6b6b', '#f06595', '#cc5de8', '#845ef7', 
            '#5c7cfa', '#339af0', '#22b8cf', '#20c997', 
            '#51cf66', '#94d82d', '#fcc419', '#ff922b'
        ]
    };

    // 1. 설정 완료 (입력창 생성)
    btnConfirm.onclick = () => {
        game.players = parseInt(document.getElementById('playerCount').value);
        const top = document.getElementById('playerInputs');
        const bottom = document.getElementById('resultInputs');
        
        top.innerHTML = ''; 
        bottom.innerHTML = '';

        for(let i=0; i<game.players; i++) {
            top.innerHTML += `
                <div class="input-box">
                    <input type="text" value="참가자 ${i+1}" id="p_${i}">
                </div>`;
            
            bottom.innerHTML += `
                <div class="input-box">
                    <input type="text" value="결과 ${i+1}" id="r_${i}" placeholder="당첨/꽝">
                    <div id="badge_${i}" class="result-badge"></div>
                </div>`;
        }

        btnGenerate.disabled = false;
        btnStart.disabled = true;
        
        // 캔버스 초기화
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    };

    // 2. 사다리 생성
    btnGenerate.onclick = () => {
        resizeCanvas();
        game.width = canvas.width;
        
        const drawWidth = game.width - (game.paddingX * 2);
        game.step = drawWidth / (game.players - 1);

        createBridges();
        drawLadder();
        
        btnStart.disabled = false;
    };

    // 3. 게임 시작 (애니메이션)
    btnStart.onclick = () => {
        btnStart.disabled = true;
        btnGenerate.disabled = true;
        btnConfirm.disabled = true; // 게임 중 설정 변경 방지

        // 결과 뱃지 초기화
        document.querySelectorAll('.result-badge').forEach(b => {
            b.classList.remove('show');
            b.innerText = '';
        });

        // 순차 출발
        for(let i=0; i<game.players; i++) {
            setTimeout(() => {
                animatePath(i);
            }, i * 600 + Math.random() * 300);
        }
    };

    // 내부 로직: 다리 생성
    function createBridges() {
        game.bridges = [];
        for(let i=0; i < game.players - 1; i++) {
            let bCount = Math.floor(Math.random() * 4) + 3; // 3~6개
            for(let j=0; j<bCount; j++) {
                let y = Math.random() * (game.height - 100) + 50;
                game.bridges.push({ col: i, y: y });
            }
        }
        game.bridges.sort((a, b) => a.y - b.y);
        
        // 간격 보정 (최소 25px)
        for(let i=1; i<game.bridges.length; i++) {
            if(game.bridges[i].y - game.bridges[i-1].y < 25) {
                game.bridges[i].y += 25;
            }
        }
    }

    // 내부 로직: 사다리 그리기 (기본 회색 선)
    function drawLadder() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        ctx.strokeStyle = '#dee2e6'; // 아주 연한 회색 (배경이 흰색이므로)
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';

        // 세로줄
        for(let i=0; i<game.players; i++) {
            let x = game.paddingX + (game.step * i);
            ctx.beginPath(); 
            ctx.moveTo(x, 20); 
            ctx.lineTo(x, game.height - 20); 
            ctx.stroke();
        }

        // 가로줄
        game.bridges.forEach(b => {
            let x = game.paddingX + (game.step * b.col);
            ctx.beginPath();
            ctx.moveTo(x, b.y);
            ctx.lineTo(x + game.step, b.y);
            ctx.stroke();
        });
    }

    // 내부 로직: 경로 애니메이션
    function animatePath(playerIdx) {
        const color = game.colors[playerIdx % game.colors.length];
        const pName = document.getElementById(`p_${playerIdx}`).value;
        
        let currentX = game.paddingX + (game.step * playerIdx);
        let currentY = 20;
        let currentCol = playerIdx;
        
        let pathPoints = [{x: currentX, y: currentY}];
        
        // 경로 계산
        while(currentY < game.height - 20) {
            let nextBridge = null;
            for(let b of game.bridges) {
                if (b.y > currentY) {
                    if (b.col === currentCol) {
                        nextBridge = { bridge: b, direction: 1 };
                        break;
                    } else if (b.col === currentCol - 1) {
                        nextBridge = { bridge: b, direction: -1 };
                        break;
                    }
                }
            }

            if (nextBridge) {
                currentY = nextBridge.bridge.y;
                pathPoints.push({x: currentX, y: currentY});
                if (nextBridge.direction === 1) {
                    currentCol++;
                    currentX += game.step;
                } else {
                    currentCol--;
                    currentX -= game.step;
                }
                pathPoints.push({x: currentX, y: currentY});
            } else {
                currentY = game.height - 20;
                pathPoints.push({x: currentX, y: currentY});
            }
        }

        // 그리기 실행
        let pointIdx = 0;
        let progress = 0;
        const speed = 6;

        function drawStep() {
            if (pointIdx >= pathPoints.length - 1) {
                finishTrace(currentCol, pName, color);
                return;
            }

            const p1 = pathPoints[pointIdx];
            const p2 = pathPoints[pointIdx + 1];
            
            const dx = p2.x - p1.x;
            const dy = p2.y - p1.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            
            progress += speed;
            
            let drawX, drawY;
            
            if (progress >= dist) {
                drawX = p2.x; drawY = p2.y;
                pointIdx++; progress = 0;
            } else {
                const ratio = progress / dist;
                drawX = p1.x + dx * ratio;
                drawY = p1.y + dy * ratio;
            }

            ctx.strokeStyle = color;
            ctx.lineWidth = 5;
            ctx.lineCap = 'round';
            ctx.shadowBlur = 0; // 깔끔함을 위해 그림자 제거
            
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y); 
            if(progress < dist) ctx.lineTo(drawX, drawY);
            else ctx.lineTo(p2.x, p2.y);
            ctx.stroke();

            requestAnimationFrame(drawStep);
        }
        drawStep();
    }

    function finishTrace(resultColIdx, pName, color) {
        const resInput = document.getElementById(`r_${resultColIdx}`);
        const badge = document.getElementById(`badge_${resultColIdx}`);
        
        // 결과창 테두리 강조
        resInput.style.borderColor = color;
        resInput.style.borderWidth = '3px';
        
        // 뱃지 표시
        badge.innerText = pName;
        badge.style.backgroundColor = color;
        badge.classList.add('show');
        
        // 모든 참가자 도착 시 리셋 버튼 활성화 로직 등 추가 가능
        // 현재는 단순 일회성
    }
});