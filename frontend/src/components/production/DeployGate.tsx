import { useState } from 'react';
import {
  Rocket,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Shield,
  TestTube,
  Eye,
  Settings,
  Activity,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Modal } from '@/components/common/Modal';

interface StagingCheckResult {
  label: string;
  passed: boolean;
  detail?: string;
}

interface DeployGateProps {
  isPmLead: boolean;
  stagingChecks: StagingCheckResult[];
  onDeploy: (config: { canary_percent: number }) => Promise<void>;
  disabled?: boolean;
}

const CANARY_OPTIONS = [5, 10, 25, 50];

export function DeployGate({
  isPmLead,
  stagingChecks,
  onDeploy,
  disabled = false,
}: DeployGateProps) {
  const [showModal, setShowModal] = useState(false);
  const [canaryPercent, setCanaryPercent] = useState(5);
  const [isDeploying, setIsDeploying] = useState(false);
  const [checklist, setChecklist] = useState<Record<string, boolean>>({
    reviewed: false,
    tested: false,
    monitoring: false,
  });

  const allStagingPassed = stagingChecks.every((c) => c.passed);
  const allChecklistDone = Object.values(checklist).every(Boolean);

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      await onDeploy({ canary_percent: canaryPercent });
      setShowModal(false);
    } finally {
      setIsDeploying(false);
    }
  };

  const toggleChecklist = (key: string) => {
    setChecklist((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (!isPmLead) {
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-5 text-center">
        <Shield className="mx-auto h-8 w-8 text-gray-400 mb-2" />
        <p className="text-sm text-gray-500">
          Only PM Lead can deploy to production.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Rocket className="h-5 w-5 text-brand-600" />
            <h3 className="text-sm font-semibold text-gray-900">Deploy to Production</h3>
          </div>
          <Badge variant={allStagingPassed ? 'success' : 'danger'}>
            {allStagingPassed ? 'Ready' : 'Not Ready'}
          </Badge>
        </div>

        {/* Staging test results summary */}
        <div className="mb-4 space-y-2">
          {stagingChecks.map((check, idx) => (
            <div
              key={idx}
              className="flex items-center gap-3 rounded-lg border border-gray-100 px-3 py-2"
            >
              {check.passed ? (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 text-red-600 shrink-0" />
              )}
              <span className="flex-1 text-sm text-gray-700">{check.label}</span>
              {check.detail && (
                <span className="text-xs text-gray-400">{check.detail}</span>
              )}
            </div>
          ))}
        </div>

        {/* Deploy button */}
        <Button
          icon={<Rocket className="h-4 w-4" />}
          onClick={() => setShowModal(true)}
          disabled={disabled || !allStagingPassed}
          className="w-full"
        >
          Deploy to Production
        </Button>

        {!allStagingPassed && (
          <p className="mt-2 text-xs text-red-500 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            All staging checks must pass before deploying.
          </p>
        )}
      </div>

      {/* Confirmation modal */}
      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title="Confirm Production Deployment"
        maxWidth="max-w-md"
      >
        <div className="space-y-4">
          {/* Pre-deploy checklist */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Pre-deploy Checklist</p>
            <div className="space-y-2">
              {[
                { key: 'reviewed', icon: Eye, label: 'Changes have been reviewed and approved' },
                { key: 'tested', icon: TestTube, label: 'All tests pass on staging' },
                { key: 'monitoring', icon: Activity, label: 'Monitoring and alerts are configured' },
              ].map(({ key, icon: Icon, label }) => (
                <label
                  key={key}
                  className="flex items-center gap-3 rounded-lg border border-gray-200 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={checklist[key]}
                    onChange={() => toggleChecklist(key)}
                    className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                  />
                  <Icon className="h-4 w-4 text-gray-400 shrink-0" />
                  <span className="text-sm text-gray-700">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Canary configuration */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1.5">
              <Settings className="h-4 w-4 text-gray-400" />
              Canary Configuration
            </p>
            <div className="flex gap-2">
              {CANARY_OPTIONS.map((pct) => (
                <button
                  key={pct}
                  onClick={() => setCanaryPercent(pct)}
                  className={clsx(
                    'flex-1 rounded-lg border py-2 text-sm font-medium transition-colors',
                    canaryPercent === pct
                      ? 'border-brand-500 bg-brand-50 text-brand-700'
                      : 'border-gray-200 text-gray-500 hover:bg-gray-50',
                  )}
                >
                  {pct}%
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-gray-400">
              Initial canary traffic percentage. Will auto-promote through stages.
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t border-gray-200">
            <Button variant="ghost" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button
              icon={<Rocket className="h-4 w-4" />}
              onClick={handleDeploy}
              loading={isDeploying}
              disabled={!allChecklistDone}
            >
              Deploy ({canaryPercent}% Canary)
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

