import { useState, useEffect, useCallback } from 'react';
import {
  BarChart3,
  TrendingUp,
  Clock,
  CheckCircle,
  Bot,
  Shield,
  Rocket,
  RotateCcw,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Spinner } from '@/components/common/Spinner';
import * as dashboardApi from '@/api/dashboard';

type ActiveTab = 'overview' | 'pipeline' | 'ai_costs' | 'quality' | 'deployments';

const TABS: { id: ActiveTab; label: string; icon: typeof BarChart3 }[] = [
  { id: 'overview', label: 'Overview', icon: BarChart3 },
  { id: 'pipeline', label: 'Pipeline', icon: TrendingUp },
  { id: 'ai_costs', label: 'AI Costs', icon: Bot },
  { id: 'quality', label: 'Code Quality', icon: Shield },
  { id: 'deployments', label: 'Deployments', icon: Rocket },
];

function formatHours(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

// Default project ID — in production this would come from project selector
const DEFAULT_PROJECT_ID = 'default';

export function MetricsDashboard() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [pipelineData, setPipelineData] = useState<dashboardApi.PipelineStatsResponse | null>(null);
  const [aiCostData, setAiCostData] = useState<dashboardApi.AiCostsResponse | null>(null);
  const [qualityData, setQualityData] = useState<dashboardApi.CodeQualityResponse | null>(null);
  const [deployData, setDeployData] = useState<dashboardApi.DeploymentStatsResponse | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const params = { project_id: DEFAULT_PROJECT_ID };
    try {
      const [pipeline, aiCosts, quality, deploys] = await Promise.all([
        dashboardApi.pipelineStats(params),
        dashboardApi.aiCosts(params),
        dashboardApi.codeQuality(params),
        dashboardApi.deploymentStats(params),
      ]);
      setPipelineData(pipeline);
      setAiCostData(aiCosts);
      setQualityData(quality);
      setDeployData(deploys);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        'Failed to load dashboard data';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500">Pipeline metrics and analytics</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={fetchData}
            loading={isLoading}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="flex gap-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'border-brand-600 text-brand-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : error ? (
        <div className="flex h-64 items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-semibold text-red-600">Error</p>
            <p className="mt-1 text-sm text-gray-500">{error}</p>
            <Button variant="secondary" className="mt-4" onClick={fetchData}>
              Retry
            </Button>
          </div>
        </div>
      ) : (
        <>
          {/* Overview tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Top-level metric cards */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                <MetricCard
                  label="Total Tickets"
                  value={pipelineData?.total_tickets ?? 0}
                  icon={BarChart3}
                  color="bg-blue-50 text-blue-600"
                />
                <MetricCard
                  label="Avg Cycle Time"
                  value={
                    pipelineData?.avg_time_per_column_hours
                      ? formatHours(
                          Object.values(pipelineData.avg_time_per_column_hours).reduce(
                            (a, b) => a + b,
                            0,
                          ),
                        )
                      : '--'
                  }
                  icon={Clock}
                  color="bg-purple-50 text-purple-600"
                />
                <MetricCard
                  label="AI Cost"
                  value={`$${(aiCostData?.total_cost ?? 0).toFixed(2)}`}
                  icon={Bot}
                  color="bg-brand-50 text-brand-600"
                />
                <MetricCard
                  label="Tokens Used"
                  value={aiCostData?.tokens_total ?? 0}
                  icon={TrendingUp}
                  color="bg-orange-50 text-orange-600"
                />
                <MetricCard
                  label="Deploy Success"
                  value={`${((deployData?.success_rate ?? 0) * 100).toFixed(0)}%`}
                  icon={Rocket}
                  color="bg-green-50 text-green-600"
                />
                <MetricCard
                  label="Vulnerabilities"
                  value={qualityData?.security_vuln_count ?? 0}
                  icon={Shield}
                  color={
                    (qualityData?.security_vuln_count ?? 0) === 0
                      ? 'bg-green-50 text-green-600'
                      : 'bg-red-50 text-red-600'
                  }
                />
              </div>

              {/* Two-column chart layout */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* AI Cost by Agent */}
                {aiCostData && (
                  <div className="rounded-xl border border-gray-200 bg-white p-5">
                    <h3 className="mb-4 text-sm font-semibold text-gray-700">AI Cost by Agent</h3>
                    <div className="space-y-3">
                      {Object.entries(aiCostData.cost_by_agent).map(([agent, costUsd], idx) => {
                        const maxCost = Math.max(
                          ...Object.values(aiCostData.cost_by_agent),
                          1,
                        );
                        const pct = (costUsd / maxCost) * 100;
                        return (
                          <div key={agent}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-gray-700">{agent}</span>
                              <span className="text-xs text-gray-500">${costUsd.toFixed(2)}</span>
                            </div>
                            <div className="h-3 w-full rounded-full bg-gray-100 overflow-hidden">
                              <div
                                className={clsx(
                                  'h-full rounded-full',
                                  [
                                    'bg-brand-600',
                                    'bg-blue-500',
                                    'bg-purple-500',
                                    'bg-orange-500',
                                    'bg-green-500',
                                  ][idx % 5],
                                )}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Deployment stats */}
                {deployData && (
                  <div className="rounded-xl border border-gray-200 bg-white p-5">
                    <h3 className="mb-4 text-sm font-semibold text-gray-700">Deployment Overview</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="text-center">
                        <p className="text-3xl font-bold text-gray-900">
                          {deployData.deploy_count}
                        </p>
                        <p className="text-xs text-gray-500">Total Deploys</p>
                      </div>
                      <div className="text-center">
                        <p className="text-3xl font-bold text-green-600">
                          {(deployData.success_rate * 100).toFixed(0)}%
                        </p>
                        <p className="text-xs text-gray-500">Success Rate</p>
                      </div>
                      <div className="text-center">
                        <p className="text-3xl font-bold text-red-600">
                          {(deployData.rollback_rate * 100).toFixed(1)}%
                        </p>
                        <p className="text-xs text-gray-500">Rollback Rate</p>
                      </div>
                      <div className="text-center">
                        <p className="text-3xl font-bold text-gray-900">
                          {Math.round(deployData.avg_deploy_time_ms / 60000)}m
                        </p>
                        <p className="text-xs text-gray-500">Avg Deploy Time</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Pipeline tab */}
          {activeTab === 'pipeline' && pipelineData && (
            <div className="space-y-6">
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h4 className="text-sm font-semibold text-gray-900 mb-4">Tickets Per Column</h4>
                <div className="space-y-3">
                  {Object.entries(pipelineData.tickets_per_column).map(([col, count]) => (
                    <div key={col} className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-36 shrink-0">
                        {col
                          .split('_')
                          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                          .join(' ')}
                      </span>
                      <div className="flex-1 h-4 rounded bg-gray-100 overflow-hidden">
                        <div
                          className="h-full rounded bg-brand-500"
                          style={{
                            width: `${
                              pipelineData.total_tickets > 0
                                ? (count / pipelineData.total_tickets) * 100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-bold text-gray-700 w-8 text-right">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {pipelineData.avg_time_per_column_hours && (
                <div className="rounded-xl border border-gray-200 bg-white p-5">
                  <h4 className="text-sm font-semibold text-gray-900 mb-4">
                    Average Time Per Column
                  </h4>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(pipelineData.avg_time_per_column_hours).map(
                      ([col, hours]) => (
                        <div
                          key={col}
                          className="rounded bg-gray-50 px-3 py-2 text-center"
                        >
                          <p className="text-xs text-gray-500 mb-1">
                            {col
                              .split('_')
                              .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                              .join(' ')}
                          </p>
                          <p className="text-sm font-bold text-gray-900">
                            {formatHours(hours)}
                          </p>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI Costs tab */}
          {activeTab === 'ai_costs' && aiCostData && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <MetricCard
                  label="Total Cost"
                  value={`$${aiCostData.total_cost.toFixed(2)}`}
                  icon={Bot}
                  color="bg-brand-50 text-brand-600"
                />
                <MetricCard
                  label="Total Tokens"
                  value={aiCostData.tokens_total.toLocaleString()}
                  icon={TrendingUp}
                  color="bg-blue-50 text-blue-600"
                />
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h4 className="text-sm font-semibold text-gray-900 mb-4">Cost by Agent</h4>
                <div className="space-y-3">
                  {Object.entries(aiCostData.cost_by_agent).map(([agent, cost]) => (
                    <div key={agent} className="flex items-center justify-between">
                      <span className="text-sm text-gray-700">{agent}</span>
                      <span className="text-sm font-bold text-gray-900">${cost.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h4 className="text-sm font-semibold text-gray-900 mb-4">Cost by Day</h4>
                <div className="space-y-2">
                  {Object.entries(aiCostData.cost_by_day).map(([day, cost]) => (
                    <div key={day} className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">{day}</span>
                      <span className="text-xs font-bold text-gray-700">${cost.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Code Quality tab */}
          {activeTab === 'quality' && qualityData && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <MetricCard
                label="Lint Pass Rate"
                value={`${(qualityData.lint_pass_rate * 100).toFixed(0)}%`}
                icon={CheckCircle}
                color="bg-green-50 text-green-600"
              />
              <MetricCard
                label="Test Coverage"
                value={`${qualityData.test_coverage_avg.toFixed(1)}%`}
                icon={Shield}
                color="bg-blue-50 text-blue-600"
              />
              <MetricCard
                label="Review Pass Rate"
                value={`${(qualityData.review_pass_rate * 100).toFixed(0)}%`}
                icon={CheckCircle}
                color="bg-purple-50 text-purple-600"
              />
              <MetricCard
                label="Vulnerabilities"
                value={qualityData.security_vuln_count}
                icon={Shield}
                color={
                  qualityData.security_vuln_count === 0
                    ? 'bg-green-50 text-green-600'
                    : 'bg-red-50 text-red-600'
                }
              />
            </div>
          )}

          {/* Deployments tab */}
          {activeTab === 'deployments' && deployData && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <MetricCard
                label="Total Deploys"
                value={deployData.deploy_count}
                icon={Rocket}
                color="bg-blue-50 text-blue-600"
              />
              <MetricCard
                label="Success Rate"
                value={`${(deployData.success_rate * 100).toFixed(0)}%`}
                icon={CheckCircle}
                color="bg-green-50 text-green-600"
              />
              <MetricCard
                label="Rollback Rate"
                value={`${(deployData.rollback_rate * 100).toFixed(1)}%`}
                icon={RotateCcw}
                color="bg-red-50 text-red-600"
              />
              <MetricCard
                label="Avg Deploy Time"
                value={`${Math.round(deployData.avg_deploy_time_ms / 60000)}m`}
                icon={Clock}
                color="bg-purple-50 text-purple-600"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── MetricCard sub-component ─── */
function MetricCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: typeof BarChart3;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${color}`}>
          <Icon className="h-6 w-6" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        </div>
      </div>
    </div>
  );
}
