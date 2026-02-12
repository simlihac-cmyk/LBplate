/**
 * LBplate Daily Pick System
 * JSON 데이터 파일에서 무작위 문구를 가져와 화면에 출력합니다.
 */

async function showFortune() {
    const displayArea = document.getElementById('fortune-display');
    const titleArea = document.getElementById('fortune-title');
    
    // 1. 클릭 즉시 반응을 위한 상태 변경
    displayArea.style.opacity = 0; // 부드러운 전환을 위해 투명도 조절

    try {
        // 2. JSON 데이터 파일 가져오기
        const response = await fetch('/static/core/json/quotes.json?v=' + new Date().getTime());
        
        if (!response.ok) {
            throw new Error(`네트워크 응답 에러 (상태: ${response.status})`);
        }

        const data = await response.json();
        const fortunes = data.daily_insights;

        // 3. 중복을 피하기 위해 랜덤 인덱스 선택
        const randomIndex = Math.floor(Math.random() * fortunes.length);
        const selectedFortune = fortunes[randomIndex];

        // 4. 짧은 지연 후 텍스트 교체 (애니메이션 효과)
        setTimeout(() => {
            titleArea.innerText = "Today's Insight";
            displayArea.innerText = selectedFortune;
            
            // 디자인 테마에 맞춘 스타일 조정
            displayArea.style.opacity = 1;
            displayArea.style.color = "var(--text-main)";
            displayArea.style.fontSize = "0.95rem";
            displayArea.style.fontWeight = "500";
        }, 300);

    } catch (error) {
        console.error("LBplate Error:", error);
        displayArea.innerText = "문구를 불러올 수 없습니다. 경로를 확인하세요.";
        displayArea.style.opacity = 1;
    }
}

// 스크립트 로드 확인용 로그
console.log("LBplate: Daily Pick System Ready.");