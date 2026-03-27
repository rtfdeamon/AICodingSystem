import { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Lightbulb,
  Paintbrush,
  Reply,
  Send,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Avatar } from '@/components/common/Avatar';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';

type Severity = 'critical' | 'warning' | 'suggestion' | 'style';

export interface InlineCommentData {
  id: string;
  author: {
    name: string;
    avatar_url?: string;
  };
  severity: Severity;
  body: string;
  created_at: string;
  replies?: InlineCommentData[];
}

interface InlineCommentProps {
  comment: InlineCommentData;
  onReply?: (commentId: string, body: string) => Promise<void>;
}

const severityConfig: Record<Severity, {
  icon: typeof AlertCircle;
  color: string;
  bgColor: string;
  label: string;
  variant: 'danger' | 'warning' | 'primary' | 'purple';
}> = {
  critical: { icon: AlertCircle, color: 'text-red-600', bgColor: 'bg-red-50', label: 'Critical', variant: 'danger' },
  warning: { icon: AlertTriangle, color: 'text-yellow-600', bgColor: 'bg-yellow-50', label: 'Warning', variant: 'warning' },
  suggestion: { icon: Lightbulb, color: 'text-blue-600', bgColor: 'bg-blue-50', label: 'Suggestion', variant: 'primary' },
  style: { icon: Paintbrush, color: 'text-purple-600', bgColor: 'bg-purple-50', label: 'Style', variant: 'purple' },
};

function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function InlineComment({ comment, onReply }: InlineCommentProps) {
  const [showReply, setShowReply] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const config = severityConfig[comment.severity];
  const SevIcon = config.icon;

  const handleSubmitReply = async () => {
    if (!replyText.trim() || !onReply) return;
    setIsSubmitting(true);
    try {
      await onReply(comment.id, replyText.trim());
      setReplyText('');
      setShowReply(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={clsx('rounded-lg border-l-4 bg-white shadow-sm', {
      'border-l-red-500': comment.severity === 'critical',
      'border-l-yellow-500': comment.severity === 'warning',
      'border-l-blue-500': comment.severity === 'suggestion',
      'border-l-purple-500': comment.severity === 'style',
    })}>
      <div className="p-3">
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <Avatar name={comment.author.name} src={comment.author.avatar_url} size="sm" />
          <span className="text-sm font-medium text-gray-900">{comment.author.name}</span>
          <Badge variant={config.variant}>
            <SevIcon className="h-3 w-3 mr-0.5" />
            {config.label}
          </Badge>
          <span className="ml-auto text-[10px] text-gray-400">
            {formatTime(comment.created_at)}
          </span>
        </div>

        {/* Comment body */}
        <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
          {comment.body}
        </p>

        {/* Reply toggle */}
        {onReply && (
          <button
            onClick={() => setShowReply(!showReply)}
            className="mt-2 inline-flex items-center gap-1 text-xs text-gray-500 hover:text-brand-600 transition-colors"
          >
            <Reply className="h-3 w-3" />
            Reply
          </button>
        )}
      </div>

      {/* Replies */}
      {comment.replies && comment.replies.length > 0 && (
        <div className="border-t border-gray-100 bg-gray-50/50 px-3 py-2 space-y-2">
          {comment.replies.map((reply) => (
            <div key={reply.id} className="flex items-start gap-2 pl-4">
              <Avatar name={reply.author.name} src={reply.author.avatar_url} size="sm" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-900">{reply.author.name}</span>
                  <span className="text-[10px] text-gray-400">{formatTime(reply.created_at)}</span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">{reply.body}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reply input */}
      {showReply && (
        <div className="border-t border-gray-100 p-3">
          <div className="flex gap-2">
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Write a reply..."
              rows={2}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-xs text-gray-900 placeholder-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  handleSubmitReply();
                }
              }}
            />
            <Button
              size="sm"
              icon={<Send className="h-3 w-3" />}
              onClick={handleSubmitReply}
              loading={isSubmitting}
              disabled={!replyText.trim()}
            >
              Send
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
