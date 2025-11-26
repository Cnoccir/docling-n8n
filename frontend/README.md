# Docling Dashboard - Frontend

React-based dashboard for document ingestion monitoring and management.

## Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **React Router** - Routing
- **Zustand** - State management
- **Axios** - HTTP client
- **React Dropzone** - File upload
- **Lucide React** - Icons

## Development

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

Access at: http://localhost:3000

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## Docker

### Production Build

```bash
docker build -t docling-frontend .
docker run -p 3000:80 docling-frontend
```

### With Docker Compose

From project root:

```bash
docker-compose -f docker-compose.dashboard.yml up frontend
```

## Project Structure

```
frontend/
├── src/
│   ├── components/      # Reusable UI components
│   │   ├── Layout.tsx
│   │   ├── StatCard.tsx
│   │   └── ProgressBar.tsx
│   ├── pages/           # Page components
│   │   ├── Dashboard.tsx
│   │   ├── Upload.tsx
│   │   ├── QueueManager.tsx
│   │   └── Documents.tsx
│   ├── services/        # API & WebSocket clients
│   │   ├── api.ts
│   │   └── websocket.ts
│   ├── store/           # Zustand state management
│   │   └── index.ts
│   ├── types/           # TypeScript types
│   │   └── index.ts
│   ├── utils/           # Utility functions
│   │   └── format.ts
│   ├── App.tsx          # Main app component
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── index.html           # HTML template
├── vite.config.ts       # Vite configuration
├── tailwind.config.js   # TailwindCSS configuration
├── tsconfig.json        # TypeScript configuration
└── Dockerfile           # Production Docker image
```

## Features

### Dashboard
- Real-time queue statistics
- Recent jobs list with live updates
- Quick action cards
- WebSocket connection for live data

### Upload
- Drag-and-drop file upload
- Single and bulk upload (up to 50 files)
- Metadata tagging (document type, tags)
- Upload progress tracking

### Queue Manager
- Job list with status filters
- Real-time progress updates via WebSocket
- Cancel running jobs
- Retry failed jobs
- Job statistics (pages, chunks, cost, duration)

### Document Library
- Document grid with filters
- Search by filename
- Status filtering
- Document metadata display
- Tags and categories

## Environment Variables

Create `.env.local` for development:

```bash
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000
```

## API Integration

The frontend connects to the FastAPI backend at `/api` and WebSocket at `/ws`.

In production (Docker), nginx proxies these requests to the backend service.

## WebSocket Updates

Real-time job progress updates are received via WebSocket:

```typescript
websocketClient.connect();

websocketClient.onJobUpdate((update) => {
  console.log(update.job_id, update.progress, update.status);
});
```

## State Management

Zustand store manages global state:

- Jobs list
- Queue statistics
- Active workers
- Loading/error states

## Styling

TailwindCSS with custom components:

- `.card` - White card with shadow
- `.btn-primary` - Primary blue button
- `.btn-secondary` - Secondary gray button
- `.btn-danger` - Red danger button
- `.badge-*` - Status badges

## Building

The production build uses:

1. **Vite** - Bundles React app
2. **Multi-stage Docker** - Optimizes image size
3. **Nginx** - Serves static files & proxies API

Final image size: ~25MB

## Browser Support

- Chrome/Edge (last 2 versions)
- Firefox (last 2 versions)
- Safari (last 2 versions)

## License

See main project LICENSE
