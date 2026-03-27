import { ExternalLink, Mail, Phone, MapPin, Send } from 'lucide-react';

export function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {/* Header */}
      <div className="flex items-center gap-5 mb-8">
        <img
          src="/logo-devbot.webp"
          alt="Dev-bot"
          className="h-20 w-20 rounded-2xl object-contain shadow-md"
        />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Coding Pipeline</h1>
          <p className="text-sm text-gray-500 mt-1">
            by <span className="font-semibold text-brand-600">Dev-bot</span> &mdash; dev-bot.su
          </p>
        </div>
      </div>

      {/* About the System */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">About the System</h2>
        <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-700 leading-relaxed space-y-3">
          <p>
            <strong>AI Coding Pipeline</strong> is an intelligent project management and development
            automation platform. The system orchestrates AI agents (Claude, GPT, Gemini) to handle
            planning, code generation, testing, security review, and deployment workflows.
          </p>
          <p>
            Built with a modular architecture featuring n8n workflow integrations, real-time
            WebSocket updates, Kanban board management, and comprehensive AI cost tracking.
          </p>
        </div>
      </section>

      {/* About the Developers */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Developers</h2>
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="flex items-start gap-4">
            <img
              src="/logo-devbot.webp"
              alt="Dev-bot"
              className="h-14 w-14 rounded-xl object-contain"
            />
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900">Dev-bot</h3>
              <p className="text-sm text-gray-600 mt-1">
                Development of intelligent chatbots, AI implementation, and business process
                automation. Over 10 years of experience implementing AI solutions with 100+
                completed projects across retail, logistics, manufacturing, finance, education, and
                government sectors.
              </p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <a
              href="https://dev-bot.su"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <ExternalLink className="h-4 w-4 text-brand-600" />
              dev-bot.su
            </a>
            <a
              href="mailto:sales@4key.team"
              className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Mail className="h-4 w-4 text-brand-600" />
              sales@4key.team
            </a>
            <a
              href="tel:+73432264562"
              className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Phone className="h-4 w-4 text-brand-600" />
              +7-343-226-45-62
            </a>
            <a
              href="https://t.me/AlexGrekhov"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Send className="h-4 w-4 text-brand-600" />
              Telegram
            </a>
          </div>

          <div className="mt-4 flex items-start gap-2 text-sm text-gray-500">
            <MapPin className="h-4 w-4 mt-0.5 shrink-0" />
            <span>Ekaterinburg, Russia</span>
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Tech Stack</h2>
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <h4 className="font-medium text-gray-900 mb-2">Frontend</h4>
              <ul className="space-y-1 text-gray-600">
                <li>React 18 + TypeScript</li>
                <li>Tailwind CSS</li>
                <li>Zustand + React Query</li>
                <li>Vite</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-gray-900 mb-2">Backend</h4>
              <ul className="space-y-1 text-gray-600">
                <li>Python + FastAPI</li>
                <li>SQLAlchemy + PostgreSQL</li>
                <li>Redis + WebSockets</li>
                <li>n8n Integration</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-gray-900 mb-2">AI Agents</h4>
              <ul className="space-y-1 text-gray-600">
                <li>Claude (Anthropic)</li>
                <li>GPT (OpenAI)</li>
                <li>Gemini (Google)</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-gray-900 mb-2">Infrastructure</h4>
              <ul className="space-y-1 text-gray-600">
                <li>Docker</li>
                <li>GitHub Actions CI/CD</li>
                <li>n8n Workflow Engine</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <p className="mt-8 text-center text-xs text-gray-400">
        &copy; {new Date().getFullYear()} Dev-bot. All rights reserved.
      </p>
    </div>
  );
}
