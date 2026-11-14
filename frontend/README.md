# IRIS Frontend — Student Chat Interface

A polished, responsive React + TypeScript web application for the IRIS (Information Retrieval and Intelligence System) institutional document assistant at PEC.

## Architecture

- **Framework**: React 19 + TypeScript + Vite
- **Icons**: Lucide React
- **Markdown**: `react-markdown` (safe, client-side rendering with no arbitrary HTML)
- **Testing**: Vitest + React Testing Library + jsdom
- **API Communication**: Dedicated typed service layer connecting exclusively to FastAPI backend (`POST /chat`, `GET /health`)

## Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Chat/
│   │   │   ├── ChatContainer.tsx    # Layout container and scroll manager
│   │   │   └── WelcomeScreen.tsx    # Hero greeting and 4 clickable corpus suggestions
│   │   ├── Citation/
│   │   │   ├── CitationItem.tsx     # Single source card with filename & page ranges
│   │   │   └── CitationList.tsx     # Expandable collection of grounded sources
│   │   ├── Input/
│   │   │   └── MessageComposer.tsx  # Multiline textarea, Enter-to-send, char limit
│   │   ├── Layout/
│   │   │   ├── Footer.tsx           # Institutional disclaimer
│   │   │   ├── Header.tsx           # Brand identity and new-chat button
│   │   │   └── StatusBadge.tsx      # Connected / Disconnected / Checking indicator
│   │   └── Message/
│   │       ├── AnsweredCard.tsx     # Markdown answer + citations
│   │       ├── ClarificationCard.tsx # Visually distinct course/code query card
│   │       ├── ErrorCard.tsx        # Friendly failure card with retry button
│   │       ├── HandoffCard.tsx      # Calming institutional office recommendation
│   │       ├── MessageItem.tsx      # Message row dispatcher (user vs assistant)
│   │       └── MessageList.tsx      # Auto-scrolling chat history + loader
│   ├── hooks/
│   │   ├── useChat.ts               # In-memory chat state and submission handler
│   │   └── useHealth.ts             # Backend liveness checking
│   ├── services/
│   │   └── api.ts                   # Fetch API wrapper with error mapping
│   ├── test/
│   │   ├── App.test.tsx             # End-to-end user flow integration tests
│   │   ├── api.test.ts              # Service and error mapping tests
│   │   ├── components.test.tsx      # Unit tests for UI components
│   │   └── setup.ts                 # Test environment setup
│   ├── types/
│   │   ├── api.ts                   # Backend schema types
│   │   └── chat.ts                  # Internal UI chat types
│   ├── App.tsx                      # Root shell
│   ├── index.css                    # Academic design system styling
│   └── main.tsx                     # React entrypoint
├── .env.example
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Running Locally

### 1. Configure Environment
Copy `.env.example` to `.env` if custom backend URL is desired (defaults to `http://127.0.0.1:8000`):
```bash
cp .env.example .env
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Start Development Server
```bash
npm run dev
```
The application will be available at `http://localhost:5173`.

### 4. Run Tests
```bash
npm test
```

### 5. Build for Production
```bash
npm run build
```
