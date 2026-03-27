import { useState, useEffect } from 'react';
import { Save, FolderGit2, Key, Bell, Globe, Bot, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { useAuth } from '@/hooks/useAuth';
import { listProjects, updateProject as apiUpdateProject, type Project } from '@/api/projects';
import { COLUMN_NAMES, COLUMN_LABELS } from '@/utils/constants';

type SettingsTab = 'project' | 'ai_agents' | 'integrations' | 'notifications' | 'profile';

const tabs: { id: SettingsTab; label: string; icon: typeof Save }[] = [
  { id: 'project', label: 'Project', icon: FolderGit2 },
  { id: 'ai_agents', label: 'AI Agents', icon: Bot },
  { id: 'integrations', label: 'Integrations', icon: Key },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'profile', label: 'Profile', icon: Globe },
];

// AI stages where agents work
const AI_STAGES = [
  {
    key: 'ai_planning',
    label: 'AI Planning',
    description: 'Agent generates a development plan from the ticket description',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are an AI planning agent. Given a ticket with title and description, create a detailed development plan.\n\nInclude:\n- List of files to create/modify\n- Step-by-step implementation plan\n- Estimated complexity (low/medium/high)\n- Potential risks and mitigations\n- Test strategy`,
  },
  {
    key: 'ai_coding',
    label: 'AI Coding',
    description: 'Agent generates code based on the approved plan',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are an AI coding agent. Given an approved plan, generate production-quality code.\n\nRequirements:\n- Follow existing code style and patterns\n- Add proper error handling\n- Include TypeScript types\n- Write clean, maintainable code\n- Add inline comments for complex logic`,
  },
  {
    key: 'ai_testing',
    label: 'AI Testing',
    description: 'Agent generates and runs tests for the new code',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are an AI testing agent. Generate comprehensive tests for the code changes.\n\nInclude:\n- Unit tests for all new functions\n- Integration tests for API endpoints\n- Edge case coverage\n- Mock external dependencies\n- Target 80%+ code coverage`,
  },
  {
    key: 'ai_security',
    label: 'AI Security Review',
    description: 'Agent scans code for security vulnerabilities',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are an AI security reviewer. Analyze the code changes for security vulnerabilities.\n\nCheck for:\n- OWASP Top 10 vulnerabilities\n- SQL injection, XSS, CSRF\n- Authentication/authorization issues\n- Sensitive data exposure\n- Insecure dependencies\n- Rate limiting gaps`,
  },
  {
    key: 'ai_review',
    label: 'AI Code Review',
    description: 'Agent performs automated code review',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are an AI code reviewer. Review the code changes for quality and best practices.\n\nEvaluate:\n- Code correctness and logic\n- Performance implications\n- Error handling completeness\n- API contract compliance\n- DRY principle adherence\n- Naming conventions`,
  },
  {
    key: 'staging_deploy',
    label: 'Staging Deploy',
    description: 'Instructions for deploying to staging environment and running tests',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are a deployment agent responsible for staging deployments.\n\nDeploy steps:\n1. Merge the feature branch into staging branch\n2. Run: docker-compose -f docker-compose.staging.yml up -d --build\n3. Wait for health check: curl -f http://staging:8001/health\n4. Run database migrations: alembic upgrade head\n5. Verify all services are running\n\nTest steps:\n1. Run full test suite: pytest tests/ -v --tb=short\n2. Run E2E tests: npm run test:e2e\n3. Run load test: k6 run load-test.js\n4. Check logs for errors: docker-compose logs --tail=100\n5. Verify API endpoints respond correctly\n\nRollback:\n- If any step fails, run: docker-compose -f docker-compose.staging.yml down\n- Revert to previous image: docker-compose up -d --no-build\n- Notify team via Slack/Telegram`,
  },
  {
    key: 'staging_verification',
    label: 'Staging Verification',
    description: 'Agent verifies staging deployment quality before production',
    defaultModel: 'claude-sonnet-4-20250514',
    defaultPrompt: `You are a QA verification agent. Verify the staging deployment meets quality standards.\n\nChecklist:\n- All API endpoints return expected responses\n- No new errors in application logs\n- Performance metrics within acceptable range (p99 < 500ms)\n- All automated tests pass\n- Security scan clean\n- Database migrations applied correctly\n- Feature flags configured properly\n\nIf all checks pass, approve for production deployment.\nIf any check fails, provide detailed failure report and reject.`,
  },
];

const AVAILABLE_MODELS = [
  { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
  { value: 'claude-opus-4-20250514', label: 'Claude Opus 4' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
];

interface StageConfig {
  enabled: boolean;
  model: string;
  prompt: string;
  temperature: number;
  maxTokens: number;
  timeoutSeconds: number;
  costCapUsd: number;
}

export function SettingsPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<SettingsTab>('project');
  const [project, setProject] = useState<Project | null>(null);
  const [projectForm, setProjectForm] = useState({
    name: '',
    description: '',
    repo_url: '',
    default_branch: 'main',
  });
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [expandedStage, setExpandedStage] = useState<string | null>('ai_planning');
  const [stageConfigs, setStageConfigs] = useState<Record<string, StageConfig>>(() => {
    const configs: Record<string, StageConfig> = {};
    AI_STAGES.forEach((stage) => {
      configs[stage.key] = {
        enabled: true,
        model: stage.defaultModel,
        prompt: stage.defaultPrompt,
        temperature: 0.3,
        maxTokens: 4096,
        timeoutSeconds: 120,
        costCapUsd: 0.50,
      };
    });
    return configs;
  });

  useEffect(() => {
    listProjects().then((res) => {
      if (res.items.length > 0) {
        const p = res.items[0];
        setProject(p);
        setProjectForm({
          name: p.name || '',
          description: p.description || '',
          repo_url: p.repo_url || '',
          default_branch: p.default_branch || 'main',
        });
      }
    }).catch(() => {});
  }, []);

  const handleSaveProject = async () => {
    if (!project) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const updated = await apiUpdateProject(project.id, projectForm);
      setProject(updated);
      setSaveMessage('Settings saved successfully.');
      setTimeout(() => setSaveMessage(null), 3000);
    } catch {
      setSaveMessage('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const updateStageConfig = (key: string, field: keyof StageConfig, value: unknown) => {
    setStageConfigs((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }));
  };

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      <div className="flex gap-6">
        {/* Sidebar tabs */}
        <nav className="w-48 space-y-1 shrink-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="flex-1 rounded-xl border border-gray-200 bg-white p-6 overflow-y-auto max-h-[calc(100vh-200px)]">
          {activeTab === 'project' && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Project Settings</h2>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">
                    Project Name
                  </label>
                  <input type="text" value={projectForm.name} onChange={(e) => setProjectForm((p) => ({ ...p, name: e.target.value }))} className="input" placeholder="My Project" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Description</label>
                  <textarea value={projectForm.description} onChange={(e) => setProjectForm((p) => ({ ...p, description: e.target.value }))} className="input resize-none" rows={3} placeholder="Project description..." />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Repository URL</label>
                  <input type="url" value={projectForm.repo_url} onChange={(e) => setProjectForm((p) => ({ ...p, repo_url: e.target.value }))} className="input" placeholder="https://github.com/org/repo" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Default Branch</label>
                  <input type="text" value={projectForm.default_branch} onChange={(e) => setProjectForm((p) => ({ ...p, default_branch: e.target.value }))} className="input" placeholder="main" />
                </div>

                <h3 className="text-sm font-semibold text-gray-700 pt-4 border-t">Pipeline Columns</h3>
                <div className="grid grid-cols-2 gap-2">
                  {COLUMN_NAMES.map((col) => (
                    <div key={col} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm">
                      <div className="h-2.5 w-2.5 rounded-full bg-brand-500" />
                      <span className="text-gray-700">{COLUMN_LABELS[col]}</span>
                    </div>
                  ))}
                </div>

                {saveMessage && (
                  <div className={`rounded-lg px-4 py-2 text-sm ${saveMessage.includes('Failed') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
                    {saveMessage}
                  </div>
                )}

                <div className="pt-2">
                  <Button icon={<Save className="h-4 w-4" />} onClick={handleSaveProject} disabled={saving || !project}>
                    {saving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'ai_agents' && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">AI Agent Configuration</h2>
              <p className="text-sm text-gray-500 mb-5">
                Configure AI models, prompts, and limits for each pipeline stage
              </p>

              <div className="space-y-3">
                {AI_STAGES.map((stage) => {
                  const config = stageConfigs[stage.key];
                  const isExpanded = expandedStage === stage.key;

                  return (
                    <div
                      key={stage.key}
                      className="rounded-lg border border-gray-200 overflow-hidden"
                    >
                      {/* Header */}
                      <button
                        onClick={() => setExpandedStage(isExpanded ? null : stage.key)}
                        className="flex w-full items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`h-2.5 w-2.5 rounded-full ${config.enabled ? 'bg-green-500' : 'bg-gray-300'}`} />
                          <div className="text-left">
                            <span className="text-sm font-medium text-gray-900">{stage.label}</span>
                            <p className="text-xs text-gray-500">{stage.description}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 font-mono">
                            {config.model.split('-').slice(0, 2).join('-')}
                          </span>
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-gray-400" />
                          )}
                        </div>
                      </button>

                      {/* Expanded config */}
                      {isExpanded && (
                        <div className="border-t border-gray-200 px-4 py-4 space-y-4 bg-gray-50/50">
                          {/* Enable toggle */}
                          <label className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={config.enabled}
                              onChange={(e) => updateStageConfig(stage.key, 'enabled', e.target.checked)}
                              className="h-4 w-4 rounded border-gray-300 text-brand-600"
                            />
                            <span className="text-sm text-gray-700">Enable this stage</span>
                          </label>

                          {/* Model selection */}
                          <div>
                            <label className="mb-1.5 block text-sm font-medium text-gray-700">AI Model</label>
                            <select
                              value={config.model}
                              onChange={(e) => updateStageConfig(stage.key, 'model', e.target.value)}
                              className="input"
                            >
                              {AVAILABLE_MODELS.map((m) => (
                                <option key={m.value} value={m.value}>{m.label}</option>
                              ))}
                            </select>
                          </div>

                          {/* System prompt */}
                          <div>
                            <label className="mb-1.5 block text-sm font-medium text-gray-700">
                              System Prompt
                            </label>
                            <textarea
                              value={config.prompt}
                              onChange={(e) => updateStageConfig(stage.key, 'prompt', e.target.value)}
                              className="input resize-none font-mono text-xs"
                              rows={8}
                            />
                            <p className="mt-1 text-xs text-gray-400">
                              This prompt is sent as the system message to the AI model
                            </p>
                          </div>

                          {/* Parameters grid */}
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                                Temperature
                              </label>
                              <input
                                type="number"
                                min="0"
                                max="2"
                                step="0.1"
                                value={config.temperature}
                                onChange={(e) => updateStageConfig(stage.key, 'temperature', parseFloat(e.target.value))}
                                className="input"
                              />
                            </div>
                            <div>
                              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                                Max Tokens
                              </label>
                              <input
                                type="number"
                                min="256"
                                max="128000"
                                step="256"
                                value={config.maxTokens}
                                onChange={(e) => updateStageConfig(stage.key, 'maxTokens', parseInt(e.target.value))}
                                className="input"
                              />
                            </div>
                            <div>
                              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                                Timeout (seconds)
                              </label>
                              <input
                                type="number"
                                min="10"
                                max="600"
                                value={config.timeoutSeconds}
                                onChange={(e) => updateStageConfig(stage.key, 'timeoutSeconds', parseInt(e.target.value))}
                                className="input"
                              />
                            </div>
                            <div>
                              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                                Cost Cap (USD)
                              </label>
                              <input
                                type="number"
                                min="0.01"
                                max="100"
                                step="0.01"
                                value={config.costCapUsd}
                                onChange={(e) => updateStageConfig(stage.key, 'costCapUsd', parseFloat(e.target.value))}
                                className="input"
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="mt-6">
                <Button icon={<Save className="h-4 w-4" />}>Save AI Configuration</Button>
              </div>
            </div>
          )}

          {activeTab === 'integrations' && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Integrations</h2>
              <div className="space-y-4">
                {[
                  { name: 'n8n Workflow Engine', desc: 'Automate pipeline workflows', connected: false },
                  { name: 'GitHub', desc: 'Repository integration & OAuth', connected: false },
                  { name: 'Slack', desc: 'Notifications and alerts', connected: false },
                  { name: 'Telegram', desc: 'Bot notifications', connected: false },
                ].map((integration) => (
                  <div key={integration.name} className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
                    <div>
                      <h3 className="text-sm font-medium text-gray-900">{integration.name}</h3>
                      <p className="text-xs text-gray-500 mt-0.5">{integration.desc}</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      integration.connected ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>
                      {integration.connected ? 'Connected' : 'Not configured'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'notifications' && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Notifications</h2>
              <div className="space-y-3">
                {[
                  { label: 'Ticket assigned to me', checked: true },
                  { label: 'Ticket moved to new column', checked: true },
                  { label: 'New comment on my tickets', checked: true },
                  { label: 'AI plan completed', checked: true },
                  { label: 'Code review requested', checked: true },
                  { label: 'Deployment completed', checked: false },
                  { label: 'Test failures', checked: true },
                ].map((pref) => (
                  <label key={pref.label} className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3 cursor-pointer hover:bg-gray-50">
                    <span className="text-sm text-gray-700">{pref.label}</span>
                    <input type="checkbox" defaultChecked={pref.checked} className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                  </label>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'profile' && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Profile</h2>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Name</label>
                  <input type="text" defaultValue={user?.full_name || ''} className="input" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Email</label>
                  <input type="email" defaultValue={user?.email || ''} className="input" disabled />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Role</label>
                  <input type="text" value={user?.role || ''} className="input bg-gray-50" disabled />
                </div>
                <div className="pt-2">
                  <Button icon={<Save className="h-4 w-4" />}>Update Profile</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
