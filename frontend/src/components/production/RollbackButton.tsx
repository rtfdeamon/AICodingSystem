import { useState } from 'react';
import {
  RotateCcw,
  AlertTriangle,
  Activity,
  Gauge,
  Clock,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Modal } from '@/components/common/Modal';

interface CanaryStatus {
  current_percentage: number;
  error_rate: number;
  latency_ms: number;
  uptime_pct: number;
}

interface RollbackButtonProps {
  canaryStatus?: CanaryStatus;
  onRollback: (reason: string) => Promise<void>;
  deploymentId: string;
  disabled?: boolean;
}

export function RollbackButton({
  canaryStatus,
  onRollback,
  deploymentId,
  disabled = false,
}: RollbackButtonProps) {
  const [showModal, setShowModal] = useState(false);
  const [reason, setReason] = useState('');
  const [isRollingBack, setIsRollingBack] = useState(false);

  const handleRollback = async () => {
    if (!reason.trim()) return;
    setIsRollingBack(true);
    try {
      await onRollback(reason.trim());
      setShowModal(false);
      setReason('');
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <>
      <Button
        variant="danger"
        icon={<RotateCcw className="h-4 w-4" />}
        onClick={() => setShowModal(true)}
        disabled={disabled}
        size="md"
      >
        Emergency Rollback
      </Button>

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title="Emergency Rollback"
        maxWidth="max-w-md"
      >
        <div className="space-y-4">
          {/* Warning banner */}
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
            <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-red-800">This will rollback the current deployment</p>
              <p className="text-xs text-red-600 mt-0.5">
                All canary traffic will be reverted to the previous version immediately.
              </p>
            </div>
          </div>

          {/* Current canary status */}
          {canaryStatus && (
            <div className="rounded-lg border border-gray-200 p-4">
              <p className="text-xs font-semibold text-gray-700 mb-3">Current Canary Status</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-gray-400" />
                  <div>
                    <p className="text-xs text-gray-500">Traffic</p>
                    <p className="text-sm font-bold text-gray-900">{canaryStatus.current_percentage}%</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <AlertTriangle
                    className={clsx(
                      'h-4 w-4',
                      canaryStatus.error_rate > 1 ? 'text-red-500' : 'text-green-500',
                    )}
                  />
                  <div>
                    <p className="text-xs text-gray-500">Error Rate</p>
                    <p
                      className={clsx(
                        'text-sm font-bold',
                        canaryStatus.error_rate > 1 ? 'text-red-600' : 'text-green-600',
                      )}
                    >
                      {canaryStatus.error_rate.toFixed(2)}%
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-gray-400" />
                  <div>
                    <p className="text-xs text-gray-500">Latency p50</p>
                    <p className="text-sm font-bold text-gray-900">{canaryStatus.latency_ms}ms</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-gray-400" />
                  <div>
                    <p className="text-xs text-gray-500">Uptime</p>
                    <p className="text-sm font-bold text-gray-900">{canaryStatus.uptime_pct}%</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Reason */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              Reason for rollback <span className="text-red-500">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe why this rollback is needed..."
              rows={3}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>

          {/* Deployment ID */}
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>Deployment:</span>
            <Badge variant="default">
              <code>{deploymentId}</code>
            </Badge>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t border-gray-200">
            <Button variant="ghost" onClick={() => setShowModal(false)} disabled={isRollingBack}>
              Cancel
            </Button>
            <Button
              variant="danger"
              icon={<RotateCcw className="h-4 w-4" />}
              onClick={handleRollback}
              loading={isRollingBack}
              disabled={!reason.trim()}
            >
              Confirm Rollback
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
