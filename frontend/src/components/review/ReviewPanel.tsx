import { useState } from 'react';
import {
  Check,
  RotateCw,
  X,
  Bot,
  AlertTriangle,
  AlertCircle,
  Lightbulb,
  Paintbrush,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';

type ReviewDecision = 'approved' | 'changes_requested' | 'rejected';

export interface AiFinding {
  id: string;
  model: string;
  file: string;
  line: number;
  severity: 'critical' | 'warning' | 'suggestion' | 'style';
  message: string;
  suggestion?: string;
}

interface ReviewPanelProps {
  onSubmit: (decision: ReviewDecision, comment: string) => Promise<void>;
  aiFindings?: AiFinding[];
  onTriggerAiReview?: () => Promise<void>;
  isAiReviewLoading?: boolean;
  disabled?: boolean;
}

const severityConfig = {
  critical: { icon: AlertCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'Critical', variant: 'danger' as const },
  warning: { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'Warning', variant: 'warning' as const },
  suggestion: { icon: Lightbulb, color: 'text-blue-600', bg: 'bg-blue-50', label: 'Suggestion', variant: 'primary' as const },
  style: { icon: Paintbrush, color: 'text-purple-600', bg: 'bg-purple-50', label: 'Style', variant: 'purple' as const },
};

const severityOrder = { critical: 0, warning: 1, suggestion: 2, style: 3 };

export function ReviewPanel({
  onSubmit,
  aiFindings = [],
  onTriggerAiReview,
  isAiReviewLoading = false,
  disabled = false,
}: ReviewPanelProps) {
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showAiFindings, setShowAiFindings] = useState(true);
  const [modelFilter, setModelFilter] = useState<string | null>(null);

  const handleSubmit = async (decision: ReviewDecision) => {
    setIsSubmitting(true);
    try {
      await onSubmit(decision, comment);
      setComment('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const models = [...new Set(aiFindings.map((f) => f.model))];
  const filteredFindings = modelFilter
    ? aiFindings.filter((f) => f.model === modelFilter)
    : aiFindings;
  const sortedFindings = [...filteredFindings].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity],
  );

  const bySeverity = {
    critical: sortedFindings.filter((f) => f.severity === 'critical'),
    warning: sortedFindings.filter((f) => f.severity === 'warning'),
    suggestion: sortedFindings.filter((f) => f.severity === 'suggestion'),
    style: sortedFindings.filter((f) => f.severity === 'style'),
  };

  return (
    <div className="flex gap-6">
      {/* Main review area */}
      <div className="flex-1 space-y-4">
        {/* Comment box */}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-700">Review Comment</label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Leave a review comment..."
            rows={4}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          <Button
            icon={<Check className="h-4 w-4" />}
            onClick={() => handleSubmit('approved')}
            loading={isSubmitting}
            disabled={disabled}
            className="bg-green-600 hover:bg-green-700 focus:ring-green-500"
          >
            Approve
          </Button>
          <Button
            variant="secondary"
            icon={<RotateCw className="h-4 w-4" />}
            onClick={() => handleSubmit('changes_requested')}
            loading={isSubmitting}
            disabled={disabled || !comment.trim()}
          >
            Request Changes
          </Button>
          <Button
            variant="danger"
            icon={<X className="h-4 w-4" />}
            onClick={() => handleSubmit('rejected')}
            loading={isSubmitting}
            disabled={disabled || !comment.trim()}
          >
            Reject
          </Button>
        </div>

        {/* AI Review trigger */}
        {onTriggerAiReview && (
          <div className="pt-2 border-t border-gray-200">
            <Button
              variant="secondary"
              size="sm"
              icon={<Bot className="h-4 w-4" />}
              onClick={onTriggerAiReview}
              loading={isAiReviewLoading}
            >
              Run AI Review
            </Button>
          </div>
        )}
      </div>

      {/* AI Findings sidebar */}
      {aiFindings.length > 0 && (
        <div className="w-80 shrink-0">
          <div className="rounded-xl border border-gray-200 bg-white">
            <button
              onClick={() => setShowAiFindings(!showAiFindings)}
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-brand-600" />
                <span className="text-sm font-semibold text-gray-900">
                  AI Findings ({aiFindings.length})
                </span>
              </div>
              {showAiFindings ? (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronRight className="h-4 w-4 text-gray-400" />
              )}
            </button>

            {showAiFindings && (
              <div className="border-t border-gray-100">
                {/* Model filter tabs */}
                {models.length > 1 && (
                  <div className="flex gap-1 px-3 py-2 border-b border-gray-100">
                    <button
                      onClick={() => setModelFilter(null)}
                      className={clsx(
                        'rounded px-2 py-1 text-xs font-medium transition-colors',
                        !modelFilter ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
                      )}
                    >
                      All
                    </button>
                    {models.map((model) => (
                      <button
                        key={model}
                        onClick={() => setModelFilter(model)}
                        className={clsx(
                          'rounded px-2 py-1 text-xs font-medium transition-colors',
                          modelFilter === model ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
                        )}
                      >
                        {model}
                      </button>
                    ))}
                  </div>
                )}

                {/* Severity summary */}
                <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
                  {Object.entries(bySeverity).map(([sev, items]) => {
                    if (items.length === 0) return null;
                    const config = severityConfig[sev as keyof typeof severityConfig];
                    return (
                      <Badge key={sev} variant={config.variant}>
                        {items.length} {config.label}
                      </Badge>
                    );
                  })}
                </div>

                {/* Finding list */}
                <div className="max-h-96 overflow-y-auto divide-y divide-gray-50">
                  {sortedFindings.map((finding) => {
                    const config = severityConfig[finding.severity];
                    const SevIcon = config.icon;

                    return (
                      <div key={finding.id} className="px-3 py-2.5 hover:bg-gray-50 transition-colors">
                        <div className="flex items-start gap-2">
                          <SevIcon className={clsx('h-4 w-4 mt-0.5 shrink-0', config.color)} />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-gray-900">{finding.message}</p>
                            <p className="mt-0.5 text-[10px] text-gray-400 font-mono">
                              {finding.file}:{finding.line}
                            </p>
                            {finding.suggestion && (
                              <p className="mt-1 text-[10px] text-gray-500 bg-gray-50 rounded px-1.5 py-1">
                                {finding.suggestion}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
