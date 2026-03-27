import {
  Bot,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface AgentInfo {
  name: string;
  model: string;
  health: 'healthy' | 'degraded' | 'down';
  fallback?: string;
}

export interface AgentMapping {
  subtask_id: string;
  subtask_title: string;
  primary_agent: string;
  fallback_chain: string[];
  current_agent: string;
  switched: boolean;
}

interface AgentRouterStatusProps {
  agents: AgentInfo[];
  mappings: AgentMapping[];
}

const healthConfig = {
  healthy: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50', label: 'Healthy' },
  degraded: { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'Degraded' },
  down: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'Down' },
};

export function AgentRouterStatus({ agents, mappings }: AgentRouterStatusProps) {
  return (
    <div className="space-y-6">
      {/* Agent health cards */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-gray-900">Agent Health</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => {
            const health = healthConfig[agent.health];
            const HealthIcon = health.icon;

            return (
              <div
                key={agent.name}
                className={clsx(
                  'rounded-lg border p-4 transition-colors',
                  agent.health === 'down'
                    ? 'border-red-200 bg-red-50/50'
                    : agent.health === 'degraded'
                      ? 'border-yellow-200 bg-yellow-50/50'
                      : 'border-gray-200 bg-white',
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={clsx('flex h-10 w-10 items-center justify-center rounded-lg', health.bg)}>
                    <Bot className={clsx('h-5 w-5', health.color)} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900">{agent.name}</p>
                    <p className="text-xs text-gray-500">{agent.model}</p>
                  </div>
                  <HealthIcon className={clsx('h-5 w-5 shrink-0', health.color)} />
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <Badge
                    variant={
                      agent.health === 'healthy' ? 'success'
                        : agent.health === 'degraded' ? 'warning'
                          : 'danger'
                    }
                  >
                    {health.label}
                  </Badge>
                  {agent.fallback && (
                    <span className="text-[10px] text-gray-400">
                      Fallback: {agent.fallback}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Subtask to agent mapping */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-gray-900">Task Routing</h3>
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Subtask</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Current Agent</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Fallback Chain</th>
                <th className="px-4 py-2.5 text-center text-xs font-medium text-gray-500 w-20">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {mappings.map((mapping) => (
                <tr key={mapping.subtask_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <span className="text-sm font-medium text-gray-900">{mapping.subtask_title}</span>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={mapping.switched ? 'warning' : 'purple'}>
                      <Bot className="h-3 w-3 mr-1" />
                      {mapping.current_agent}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 flex-wrap">
                      {mapping.fallback_chain.map((agent, i) => (
                        <span key={agent} className="flex items-center gap-1">
                          <span
                            className={clsx(
                              'text-xs px-1.5 py-0.5 rounded',
                              agent === mapping.current_agent
                                ? 'bg-brand-100 text-brand-700 font-medium'
                                : 'bg-gray-100 text-gray-500',
                            )}
                          >
                            {agent}
                          </span>
                          {i < mapping.fallback_chain.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-gray-300" />
                          )}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {mapping.switched ? (
                      <span className="inline-flex items-center gap-1 text-xs text-orange-600">
                        <RefreshCw className="h-3 w-3" />
                        Switched
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-green-600">
                        <CheckCircle className="h-3 w-3" />
                        Primary
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {mappings.length === 0 && (
            <div className="py-12 text-center text-sm text-gray-400">
              No task routing configured.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
