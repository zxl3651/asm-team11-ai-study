# 소마 메이트

> 원래 잘 됐는데 꼬였습니다. 현재 토큰 고갈로 수정 불가능...

- 팀의 특강/멘토링 일정을 종합해 회의 시간을 찾을 수 있습니다.
- 나의 이전 특강/멘토링 일정을 분석해 관심 분야의 특강을 찾을 수 있습니다.
 
## 백엔드 설정범

```
cd backend

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env

UPSTAGE_API_KEY=여기에_실제_키_입력

cd backend
python main.py
```

## 확장 프로그램 설정법

```
extension/dist/ 만들기
chrome://extensions 접속
extension/dist/ 선택
```

## 사용 방법

### 확장 프로그램을 통한 홈페이지 데이터 동기화

<img width="861" height="999" alt="Image" src="https://github.com/user-attachments/assets/4a5cad0e-9be0-4463-aefe-84af35038555" />

### 팀원들의 특강/멘토링 일정들을 분석해서 회의할 수 있는 시간을 파악

<img width="863" height="858" alt="Image" src="https://github.com/user-attachments/assets/ce024fa6-8e09-4427-a8d6-04360e066253" />

### Agent Workflow의 처리 과정과 처리 경로 시각화

<img width="1725" height="996" alt="Image" src="https://github.com/user-attachments/assets/dca2ba77-36b4-44dd-958d-c29adbb85643" />