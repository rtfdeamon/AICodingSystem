import { useMemo } from 'react';
import { DollarSign, TrendingUp, Bot } from 'lucide-react';
import { clsx } from 'clsx';

export interface AgentCost {
  agent: string;
  cost_usd: number;
  percentage: number;
}

export interface DailyCost {
  date: string;
  cost_usd: number;
}

interface AiCostChartProps {
  byAgent: AgentCost[];
  byDay: DailyCost[];
  costPerTicketAvg: number;
  totalCost: number;
}

const BAR_COLORS = [
  'bg-brand-600',
  'bg-blue-500',
  'bg-purple-500',
  'bg-orange-500',
  'bg-green-500',
  'bg-pink-500',
  'bg-yellow-500',
  'bg-cyan-500',
];

export function AiCostChart({ byAgent, byDay, costPerTicketAvg, totalCost }: AiCostChartProps) {
  const maxDailyCost = useMemo(
    () => Math.max(...byDay.map((d) => d.cost_usd), 1),
    [byDay],
  );
  const maxAgentCost = useMemo(
    () => Math.max(...byAgent.map((a) => a.cost_usd), 1),
    [byAgent],
  );

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign className="h-4 w-4 text-green-600" />
            <span className="text-xs text-gray-500">Total Cost</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">${totalCost.toFixed(2)}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-4 w-4 text-blue-600" />
            <span className="text-xs text-gray-500">Per Ticket Avg</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">${costPerTicketAvg.toFixed(2)}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <Bot className="h-4 w-4 text-purple-600" />
            <span className="text-xs text-gray-500">Agents Active</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{byAgent.length}</p>
        </div>
      </div>

      {/* Cost by agent - horizontal bar chart */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Cost by Agent</h4>
        <div className="space-y-3">
          {byAgent.map((agent, idx) => (
            <div key={agent.agent}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-gray-700">{agent.agent}</span>
                <span className="text-xs text-gray-500">
                  ${agent.cost_usd.toFixed(2)} ({agent.percentage.toFixed(1)}%)
                </span>
              </div>
              <div className="h-4 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  className={clsx('h-full rounded-full transition-all duration-700', BAR_COLORS[idx % BAR_COLORS.length])}
                  style={{ width: `${(agent.cost_usd / maxAgentCost) * 100}%` }}
                />
              </div>
            </div>
          ))}
          {byAgent.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">No cost data available.</p>
          )}
        </div>
      </div>

      {/* Cost over time - bar chart */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Cost Over Time</h4>
        <div className="flex items-end gap-1 h-48">
          {byDay.map((day) => {
            const heightPct = (day.cost_usd / maxDailyCost) * 100;
            const dateLabel = new Date(day.date).toLocaleDateString('en', { month: 'short', day: 'numeric' });

            return (
              <div
                key={day.date}
                className="flex-1 flex flex-col items-center group relative"
              >
                {/* Tooltip */}
                <div className="absolute -top-8 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <div className="rounded bg-gray-900 px-2 py-1 text-[10px] text-white whitespace-nowrap">
                    ${day.cost_usd.toFixed(2)}
                  </div>
                </div>
                {/* Bar */}
                <div className="w-full flex-1 flex items-end">
                  <div
                    className="w-full rounded-t bg-brand-500 hover:bg-brand-600 transition-colors cursor-pointer min-h-[2px]"
                    style={{ height: `${Math.max(heightPct, 1)}%` }}
                  />
                </div>
                {/* Label */}
                <span className="mt-1.5 text-[9px] text-gray-400 rotate-0">{dateLabel}</span>
              </div>
            );
          })}
          {byDay.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-400">No daily data.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
