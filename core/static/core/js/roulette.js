/**
 * LBplate Roulette System - Final Version
 * 카테고리별 항목 관리 및 사용자 지정 추가 기능 포함
 */

let canvas, ctx;
let currentItems = [];
let currentRotation = 0;
let isSpinning = false;

// 기본 데이터셋
const dataSets = {
    lunch: ["밥집", "초밥", "중국집", "두루치기", "찜닭", "치킨", "커리", "부대찌개", "학식", "칼국수", "햄버거", "국밥", "분식", "파스타", "샌드위치", "브리또"],
    decision: ["YES", "NO"],
    custom: [] // 초기에는 비어있음
};

window.onload = () => {
    canvas = document.getElementById('roulette-canvas');
    if (canvas) ctx = canvas.getContext('2d');
};

// 룰렛 그리기 함수
function drawWheel(items) {
    if (!ctx || items.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.beginPath();
        ctx.arc(160, 160, 150, 0, 2 * Math.PI);
        ctx.fillStyle = "#f0f0f0";
        ctx.fill();
        ctx.fillStyle = "#aaa";
        ctx.textAlign = "center";
        ctx.font = "14px Pretendard";
        ctx.fillText("항목을 추가해주세요", 160, 165);
        return;
    }

    const numSlices = items.length;
    const sliceAngle = (2 * Math.PI) / numSlices;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    items.forEach((item, i) => {
        const startAngle = i * sliceAngle + currentRotation;
        const endAngle = (i + 1) * sliceAngle + currentRotation;

        ctx.beginPath();
        ctx.moveTo(160, 160);
        ctx.arc(160, 160, 150, startAngle, endAngle);
        ctx.fillStyle = `hsla(${(i * 360) / numSlices}, 75%, 90%, 1)`;
        ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.05)";
        ctx.stroke();

        ctx.save();
        ctx.translate(160, 160);
        ctx.rotate(startAngle + sliceAngle / 2);
        ctx.textAlign = "right";
        ctx.fillStyle = "#333";
        ctx.font = "bold 15px Pretendard";
        ctx.fillText(item, 140, 6);
        ctx.restore();
    });
}

// 카테고리 선택 함수
function selectCategory(type) {
    const section = document.getElementById('roulette-section');
    const customArea = document.getElementById('custom-input-area');
    section.style.display = 'block';
    
    // 사용자 지정일 때만 입력창 노출
    if (type === 'custom') {
        customArea.style.display = 'block';
        currentItems = dataSets.custom;
    } else {
        customArea.style.display = 'none';
        currentItems = [...dataSets[type]]; // 원본 복사
    }

    currentRotation = 0;
    const titles = { lunch: "오늘 뭐 먹지?", decision: "할까 말까?", custom: "직접 입력하기" };
    document.getElementById('selected-title').innerText = titles[type];
    document.getElementById('result-display').innerText = "";
    
    updateItemList();
    drawWheel(currentItems);
    
    setTimeout(() => {
        window.scrollTo({ top: section.offsetTop - 50, behavior: 'smooth' });
    }, 100);
}

// 사용자 지정 항목 추가 함수
function addCustomItem() {
    const input = document.getElementById('item-input');
    const value = input.value.trim();

    if (value === "") {
        alert("항목을 입력해주세요!");
        return;
    }

    if (currentItems.length >= 12) {
        alert("최대 12개까지만 추가 가능합니다.");
        return;
    }

    currentItems.push(value);
    dataSets.custom = currentItems; // 데이터 동기화
    input.value = ""; // 입력창 비우기
    input.focus();

    updateItemList();
    drawWheel(currentItems);
}

// 추가된 항목 리스트 업데이트
function updateItemList() {
    const listDiv = document.getElementById('item-list');
    if (currentItems.length > 0) {
        listDiv.innerHTML = `현재 항목: ${currentItems.join(', ')} <br> <small style="color:red; cursor:pointer;" onclick="clearCustom()">전체 삭제</small>`;
    } else {
        listDiv.innerHTML = "";
    }
}

function clearCustom() {
    currentItems = [];
    dataSets.custom = [];
    updateItemList();
    drawWheel(currentItems);
}

// 회전 실행 함수
function spinWheel() {
    if (isSpinning || currentItems.length < 2) {
        if (currentItems.length < 2) alert("최소 2개 이상의 항목이 필요합니다.");
        return;
    }
    
    isSpinning = true;
    const resultDisplay = document.getElementById('result-display');
    resultDisplay.innerText = "두구두구...";

    const spinRotation = Math.random() * 360 + 1800; 
    const startTemp = currentRotation;
    let startTime = null;
    const duration = 4000;

    function animate(currentTime) {
        if (!startTime) startTime = currentTime;
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        const easing = 1 - Math.pow(1 - progress, 4); 
        currentRotation = startTemp + (spinRotation * (Math.PI / 180)) * easing;

        drawWheel(currentItems);

        if (progress < 1) {
            requestAnimationFrame(animate);
        } else {
            isSpinning = false;
            finalizeResult();
        }
    }
    requestAnimationFrame(animate);
}

function finalizeResult() {
    const sliceAngle = (2 * Math.PI) / currentItems.length;
    const normalizedRotation = (currentRotation % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
    const winningIndex = Math.floor(
        (currentItems.length - (normalizedRotation + Math.PI / 2) / sliceAngle) % currentItems.length
    );
    
    const actualIndex = (winningIndex + currentItems.length) % currentItems.length;
    document.getElementById('result-display').innerText = `결과: ${currentItems[actualIndex]}`;
}