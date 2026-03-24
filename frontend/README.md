# Frontend

수확해조 웹 대시보드 초기 프로젝트입니다.

## Stack

- React 18
- Vite 5
- TypeScript
- React Router
- TanStack Query
- Axios

## 시작

```bash
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`으로 접속하면 기본 레이아웃과 메뉴가 보입니다.

## 환경 변수

```bash
cp .env.example .env.local
```

```env
VITE_APP_NAME=수확해조 Control Center
VITE_API_BASE_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws
```

## 주요 명령어

```bash
npm run dev
npm run lint
npm run typecheck
npm run build
```
