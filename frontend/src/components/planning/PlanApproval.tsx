import { useState } from 'react';
import { Check, X, Clock, DollarSign } from 'lucide-react';
import { Button } from '@/components/common/Button';

interface PlanApprovalProps {
  planId: string;
  estimatedCost?: number;
  generationTimeMs?: number;
  onApprove: (planId: string) => Promise<void>;
  onReject: (planId: string, comment: string) => Promise<void>;
  disabled?: boolean;
}

export function PlanApproval({
  planId,
  estimatedCost,
  generationTimeMs,
  onApprove,
  onReject,
  disabled = false,
}: PlanApprovalProps) {
  const [mode, setMode] = useState<'idle' | 'rejecting'>('idle');
  const [rejectComment, setRejectComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await onApprove(planId);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!rejectComment.trim()) return;
    setIsSubmitting(true);
    try {
      await onReject(planId, rejectComment.trim());
      setMode('idle');
      setRejectComment('');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      {/* Meta info */}
      <div className="mb-4 flex items-center gap-6 text-sm text-gray-500">
        {estimatedCost !== undefined && (
          <div className="flex items-center gap-1.5">
            <DollarSign className="h-4 w-4 text-green-500" />
            <span>Est. cost: <strong className="text-gray-900">${estimatedCost.toFixed(2)}</strong></span>
          </div>
        )}
        {generationTimeMs !== undefined && (
          <div className="flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-blue-500" />
            <span>Generated in <strong className="text-gray-900">{(generationTimeMs / 1000).toFixed(1)}s</strong></span>
          </div>
        )}
      </div>

      {mode === 'idle' ? (
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            icon={<Check className="h-4 w-4" />}
            onClick={handleApprove}
            loading={isSubmitting}
            disabled={disabled}
            className="bg-green-600 hover:bg-green-700 focus:ring-green-500"
          >
            Approve Plan
          </Button>
          <Button
            variant="danger"
            icon={<X className="h-4 w-4" />}
            onClick={() => setMode('rejecting')}
            disabled={disabled || isSubmitting}
          >
            Reject Plan
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block text-sm font-medium text-gray-700">
            Reason for rejection <span className="text-red-500">*</span>
          </label>
          <textarea
            value={rejectComment}
            onChange={(e) => setRejectComment(e.target.value)}
            placeholder="Explain what needs to change..."
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <div className="flex items-center gap-3">
            <Button
              variant="danger"
              icon={<X className="h-4 w-4" />}
              onClick={handleReject}
              loading={isSubmitting}
              disabled={!rejectComment.trim()}
            >
              Confirm Rejection
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setMode('idle');
                setRejectComment('');
              }}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
