# Reddit AI Agent - Dashboard

Next.js 14 dashboard for monitoring and managing the autonomous Reddit AI agent.

## Architecture

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Deployment**: Vercel (free tier)

## Features

The dashboard provides:

- **Activity Feed**: Real-time view of agent's Reddit interactions
- **Belief Graph**: Interactive visualization of the agent's belief system
- **Moderation Console**: Approve/reject pending posts
- **Settings Panel**: Configure agent behavior and personas
- **Analytics**: Karma tracking, token usage, and cost metrics

## Project Structure

```
frontend/
├── app/                    # Next.js 14 App Router
│   ├── activity/          # Activity feed page
│   ├── beliefs/           # Belief management page
│   ├── moderation/        # Moderation console
│   ├── settings/          # Settings page
│   └── layout.tsx         # Root layout
├── components/
│   ├── ui/                # Reusable UI components
│   ├── belief-graph.tsx   # Belief graph visualization
│   └── activity-feed.tsx  # Activity timeline
├── lib/
│   └── api-client.ts      # Type-safe API client
├── hooks/                 # Custom React hooks
└── package.json
```

## Setup

### Prerequisites

- Node.js 18+ or higher
- npm or yarn

### Installation

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your API URL
   ```

3. **Run development server**:
   ```bash
   npm run dev
   ```

Dashboard will be available at http://localhost:3000

## Development

### Available Scripts

```bash
npm run dev        # Start development server with hot reload
npm run build      # Build production bundle
npm run start      # Start production server
npm run lint       # Run ESLint
```

### Environment Variables

Create `.env.local` with:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000  # Backend API URL
```

## API Integration

The frontend uses a type-safe API client (`lib/api-client.ts`) to communicate with the FastAPI backend.

Key endpoints:
- `GET /api/v1/activity` - Fetch recent activity
- `GET /api/v1/beliefs` - Get belief graph
- `GET /api/v1/moderation/pending` - Pending posts queue
- `POST /api/v1/moderation/approve` - Approve post
- `PUT /api/v1/settings` - Update configuration

## Deployment

### Vercel (Recommended)

The dashboard is configured for zero-config deployment to Vercel.

#### Steps to Deploy:

1. **Push code to GitHub** (if not already done)

2. **Import to Vercel**:
   - Visit https://vercel.com/new
   - Select your repository
   - Vercel will auto-detect Next.js configuration

3. **Configure Environment Variables**:
   - In Vercel dashboard, go to Project Settings > Environment Variables
   - Add the following:
     ```
     NEXT_PUBLIC_API_URL=https://your-backend-api.com
     ```
   - Replace with your actual backend API URL (e.g., DigitalOcean deployment)

4. **Deploy**:
   - Click "Deploy"
   - Subsequent pushes to main branch will trigger automatic deployments

#### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL | `https://api.yourproject.com` or `http://localhost:8000` for local |

**Note**: The `NEXT_PUBLIC_` prefix exposes variables to the browser. Never include secrets here.

#### Custom Domain (Optional)

1. In Vercel dashboard, go to Project Settings > Domains
2. Add your custom domain
3. Configure DNS as instructed by Vercel

#### Production Checklist

Before deploying to production:

- [ ] Backend API is deployed and accessible
- [ ] CORS is configured on backend to allow Vercel domain
- [ ] Environment variables are set in Vercel
- [ ] Test build locally: `npm run build`
- [ ] Verify API connectivity from deployed frontend

## References

- [Next.js Documentation](https://nextjs.org/docs)
- [Backend API Documentation](../backend/README.md)
- [Technical Specification](../docs/MVP_Reddit_AI_Agent_Technical_Specification.md)
