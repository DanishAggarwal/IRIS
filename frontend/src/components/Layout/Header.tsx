import React from 'react'
import { Sparkles, Menu, LogOut, ShieldAlert, User as UserIcon } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import type { ConnectionStatus } from '../../types/chat'
import type { UserProfile } from '../../types/api'

interface HeaderProps {
  connectionStatus: ConnectionStatus
  user: UserProfile | null
  onToggleSidebar?: () => void
  onLogout?: () => void
}

export const Header: React.FC<HeaderProps> = ({
  connectionStatus,
  user,
  onToggleSidebar,
  onLogout,
}) => {
  return (
    <header className="iris-header">
      <div className="iris-header-content">
        <div className="iris-brand-group">
          {onToggleSidebar && (
            <button
              type="button"
              onClick={onToggleSidebar}
              className="iris-btn-sidebar-toggle"
              aria-label="Toggle conversation history"
              title="Conversation history"
            >
              <Menu size={18} />
            </button>
          )}

          <div className="iris-logo-mark" aria-hidden="true">
            <span className="iris-logo-text">IRIS</span>
            <Sparkles className="iris-sparkle-icon" size={14} />
          </div>

          <div className="iris-title-group">
            <div className="iris-main-title">
              <h1>Information Retrieval &amp; Intelligence System</h1>
              <span className="iris-badge-pec">PEC</span>
            </div>
            <p className="iris-subtitle">
              Your grounded institutional and academic information assistant
            </p>
          </div>
        </div>

        <div className="iris-header-actions">
          <StatusBadge status={connectionStatus} />

          {user && (
            <div className="iris-user-profile-menu">
              <div className="iris-user-pill">
                {user.profile_picture_url ? (
                  <img
                    src={user.profile_picture_url}
                    alt={user.name}
                    className="iris-user-avatar-img"
                  />
                ) : (
                  <div className="iris-user-avatar-fallback">
                    <UserIcon size={14} />
                  </div>
                )}

                <div className="iris-user-info-text">
                  <span className="iris-user-name" title={user.name}>
                    {user.name}
                  </span>
                  <div className="iris-user-role-badge">
                    {user.role === 'admin' ? (
                      <span className="iris-role-admin">
                        <ShieldAlert size={10} className="inline mr-0.5" />
                        Admin
                      </span>
                    ) : (
                      <span className="iris-role-student">PEC Student</span>
                    )}
                  </div>
                </div>
              </div>

              {onLogout && (
                <button
                  type="button"
                  onClick={onLogout}
                  className="iris-btn-logout"
                  title="Sign out of IRIS"
                  aria-label="Sign out of IRIS"
                >
                  <LogOut size={15} />
                  <span className="iris-logout-label">Sign out</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
