import { useState, FormEvent } from 'react';
import { MessageSquare, Reply, Trash2 } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Avatar } from '@/components/common/Avatar';
import { useComments, useCreateComment, useDeleteComment } from '@/hooks/useTickets';
import { useAuth } from '@/hooks/useAuth';
import { formatRelativeTime } from '@/utils/formatters';
import type { Comment } from '@/types';

interface TicketCommentsProps {
  ticketId: string;
}

function CommentItem({
  comment,
  ticketId,
  depth = 0,
}: {
  comment: Comment;
  ticketId: string;
  depth?: number;
}) {
  const [showReply, setShowReply] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const { user } = useAuth();
  const createComment = useCreateComment();
  const deleteComment = useDeleteComment();

  const handleReply = async (e: FormEvent) => {
    e.preventDefault();
    if (!replyBody.trim()) return;
    await createComment.mutateAsync({
      ticket_id: ticketId,
      body: replyBody,
      parent_id: comment.id,
    });
    setReplyBody('');
    setShowReply(false);
  };

  const isOwner = user?.id === comment.user_id;

  return (
    <div className={depth > 0 ? 'ml-8 border-l-2 border-gray-100 pl-4' : ''}>
      <div className="group rounded-lg p-3 hover:bg-gray-50 transition-colors">
        <div className="flex items-start gap-3">
          <Avatar
            name={comment.user?.full_name || 'User'}
            src={comment.user?.avatar_url}
            size="sm"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900">
                {comment.user?.full_name || 'Unknown User'}
              </span>
              <span className="text-xs text-gray-400">
                {formatRelativeTime(comment.created_at)}
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-700 whitespace-pre-wrap">
              {comment.body}
            </p>

            {/* Actions */}
            <div className="mt-2 flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
              {depth < 2 && (
                <button
                  onClick={() => setShowReply(!showReply)}
                  className="flex items-center gap-1 text-xs text-gray-500 hover:text-brand-600"
                >
                  <Reply className="h-3 w-3" />
                  Reply
                </button>
              )}
              {isOwner && (
                <button
                  onClick={() => deleteComment.mutate(comment.id)}
                  className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-600"
                >
                  <Trash2 className="h-3 w-3" />
                  Delete
                </button>
              )}
            </div>

            {/* Reply form */}
            {showReply && (
              <form onSubmit={handleReply} className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  placeholder="Write a reply..."
                  className="input flex-1 text-sm"
                  autoFocus
                />
                <Button size="sm" type="submit" loading={createComment.isPending}>
                  Reply
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>

      {/* Nested replies */}
      {comment.replies?.map((reply) => (
        <CommentItem
          key={reply.id}
          comment={reply}
          ticketId={ticketId}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

export function TicketComments({ ticketId }: TicketCommentsProps) {
  const [newComment, setNewComment] = useState('');
  const { data: comments = [], isLoading } = useComments(ticketId);
  const createComment = useCreateComment();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    await createComment.mutateAsync({
      ticket_id: ticketId,
      body: newComment,
    });
    setNewComment('');
  };

  // Build tree from flat list
  const rootComments = comments.filter((c) => !c.parent_id);
  const childMap = new Map<string, Comment[]>();
  comments.forEach((c) => {
    if (c.parent_id) {
      const existing = childMap.get(c.parent_id) || [];
      existing.push(c);
      childMap.set(c.parent_id, existing);
    }
  });

  function attachReplies(comment: Comment): Comment {
    return {
      ...comment,
      replies: (childMap.get(comment.id) || []).map(attachReplies),
    };
  }

  const tree = rootComments.map(attachReplies);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <MessageSquare className="h-5 w-5 text-gray-500" />
        <h3 className="text-lg font-semibold text-gray-900">
          Comments ({comments.length})
        </h3>
      </div>

      {/* New comment form */}
      <form onSubmit={handleSubmit} className="mb-6">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          rows={3}
          className="input resize-none mb-2"
        />
        <div className="flex justify-end">
          <Button size="sm" type="submit" loading={createComment.isPending}>
            Comment
          </Button>
        </div>
      </form>

      {/* Comment list */}
      {isLoading ? (
        <div className="text-center py-8 text-sm text-gray-500">Loading comments...</div>
      ) : tree.length === 0 ? (
        <div className="text-center py-8 text-sm text-gray-400">
          No comments yet. Be the first to comment.
        </div>
      ) : (
        <div className="space-y-1">
          {tree.map((comment) => (
            <CommentItem
              key={comment.id}
              comment={comment}
              ticketId={ticketId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
