import React, { useState } from 'react'
import { MessageSquare, Edit2, Trash2, Check, X } from 'lucide-react'
import type { ConversationSummary } from '../../types/api'

interface ConversationItemProps {
  conversation: ConversationSummary
  isActive: boolean
  onSelect: (id: string) => void
  onRename: (id: string, newTitle: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

export const ConversationItem: React.FC<ConversationItemProps> = ({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
}) => {
  const [isEditing, setIsEditing] = useState<boolean>(false)
  const [editTitle, setEditTitle] = useState<string>(conversation.title)
  const [isConfirmingDelete, setIsConfirmingDelete] = useState<boolean>(false)
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false)

  const handleSaveRename = async (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault()
    }
    const trimmed = editTitle.trim()
    if (!trimmed || trimmed === conversation.title) {
      setIsEditing(false)
      setEditTitle(conversation.title)
      return
    }

    setIsSubmitting(true)
    try {
      await onRename(conversation.id, trimmed)
      setIsEditing(false)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteConfirm = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsSubmitting(true)
    try {
      await onDelete(conversation.id)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className={`iris-sidebar-item ${isActive ? 'iris-sidebar-item-active' : ''}`}
      onClick={() => {
        if (!isEditing && !isConfirmingDelete) {
          onSelect(conversation.id)
        }
      }}
    >
      <MessageSquare size={15} className="iris-sidebar-item-icon" />

      {isEditing ? (
        <form onSubmit={handleSaveRename} className="iris-rename-form">
          <input
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            autoFocus
            className="iris-rename-input"
            disabled={isSubmitting}
            maxLength={100}
          />
          <button
            type="submit"
            className="iris-item-action-btn text-emerald-600"
            title="Save title"
            disabled={isSubmitting}
          >
            <Check size={13} />
          </button>
          <button
            type="button"
            onClick={() => {
              setIsEditing(false)
              setEditTitle(conversation.title)
            }}
            className="iris-item-action-btn text-slate-400"
            title="Cancel"
            disabled={isSubmitting}
          >
            <X size={13} />
          </button>
        </form>
      ) : isConfirmingDelete ? (
        <div className="iris-delete-confirm-box">
          <span className="iris-delete-confirm-text">Delete?</span>
          <button
            type="button"
            onClick={handleDeleteConfirm}
            className="iris-item-action-btn text-rose-600 font-bold"
            title="Confirm delete"
            disabled={isSubmitting}
          >
            <Check size={13} />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setIsConfirmingDelete(false)
            }}
            className="iris-item-action-btn text-slate-400"
            title="Cancel"
            disabled={isSubmitting}
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <span className="iris-sidebar-item-title" title={conversation.title}>
            {conversation.title}
          </span>

          <div className="iris-sidebar-item-actions">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setIsEditing(true)
              }}
              className="iris-item-action-btn"
              title="Rename conversation"
            >
              <Edit2 size={13} />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setIsConfirmingDelete(true)
              }}
              className="iris-item-action-btn text-rose-500 hover:text-rose-700"
              title="Delete conversation"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
