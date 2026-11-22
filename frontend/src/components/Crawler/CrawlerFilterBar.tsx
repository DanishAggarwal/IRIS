import React from 'react'
import { Search, RotateCw, Filter, Play, X, ArrowUpDown } from 'lucide-react'
import type { CrawlerSource } from '../../types/api'

interface CrawlerFilterBarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  selectedSource: string
  onSourceChange: (sourceId: string) => void
  selectedStatus: string
  onStatusChange: (status: string) => void
  selectedChangeStatus: string
  onChangeStatusChange: (changeStatus: string) => void
  sortBy: string
  sortOrder: 'asc' | 'desc'
  onSortChange: (sortBy: string, sortOrder: 'asc' | 'desc') => void
  sources: CrawlerSource[]
  isScanning: boolean
  onTriggerScan: () => void
  onRefresh: () => void
}

export const CrawlerFilterBar: React.FC<CrawlerFilterBarProps> = ({
  searchQuery,
  onSearchChange,
  selectedSource,
  onSourceChange,
  selectedStatus,
  onStatusChange,
  selectedChangeStatus,
  onChangeStatusChange,
  sortBy,
  sortOrder,
  onSortChange,
  sources,
  isScanning,
  onTriggerScan,
  onRefresh,
}) => {
  const currentSortKey = `${sortBy}:${sortOrder}`

  const hasActiveFilters =
    Boolean(searchQuery) ||
    Boolean(selectedSource) ||
    Boolean(selectedStatus) ||
    Boolean(selectedChangeStatus) ||
    currentSortKey !== 'discovered_at:desc'

  const clearFilters = () => {
    onSearchChange('')
    onSourceChange('')
    onStatusChange('')
    onChangeStatusChange('')
    onSortChange('discovered_at', 'desc')
  }

  const handleSortSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    const [field, order] = val.split(':') as [string, 'asc' | 'desc']
    onSortChange(field, order)
  }

  return (
    <div className="iris-crawler-filter-bar">
      <div className="iris-crawler-search-group">
        <Search size={16} className="iris-crawler-search-icon" />
        <input
          type="text"
          className="iris-crawler-search-input"
          placeholder="Search by title, meeting number, or URL..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {searchQuery && (
          <button
            type="button"
            className="iris-crawler-search-clear"
            onClick={() => onSearchChange('')}
            aria-label="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="iris-crawler-filters-group">
        <div className="iris-crawler-select-wrapper">
          <Filter size={14} className="iris-crawler-select-icon" />
          <select
            className="iris-crawler-select"
            value={selectedSource}
            onChange={(e) => onSourceChange(e.target.value)}
            aria-label="Filter by Source"
          >
            <option value="">All Sources</option>
            {sources.map((src) => (
              <option key={src.source_id} value={src.source_id}>
                {src.name}
              </option>
            ))}
          </select>
        </div>

        <div className="iris-crawler-select-wrapper">
          <select
            className="iris-crawler-select"
            value={selectedStatus}
            onChange={(e) => onStatusChange(e.target.value)}
            aria-label="Filter by Status"
          >
            <option value="">All Statuses</option>
            <option value="discovered">Discovered</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="downloading">Downloading</option>
            <option value="ingesting">Ingesting</option>
            <option value="ingested">Ingested</option>
            <option value="download_failed">Download Failed</option>
            <option value="ingest_failed">Ingestion Failed</option>
          </select>
        </div>

        <div className="iris-crawler-select-wrapper">
          <select
            className="iris-crawler-select"
            value={selectedChangeStatus}
            onChange={(e) => onChangeStatusChange(e.target.value)}
            aria-label="Filter by Change Status"
          >
            <option value="">All Changes</option>
            <option value="unchanged">Unchanged</option>
            <option value="potentially_changed">Potentially Changed</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>

        {/* Dynamic Sorting Options */}
        <div className="iris-crawler-select-wrapper">
          <ArrowUpDown size={14} className="iris-crawler-select-icon" />
          <select
            className="iris-crawler-select"
            value={currentSortKey}
            onChange={handleSortSelect}
            aria-label="Sort documents"
          >
            <option value="discovered_at:desc">Sort: Newest First</option>
            <option value="discovered_at:asc">Sort: Oldest First</option>
            <option value="title:asc">Sort: Title (A → Z)</option>
            <option value="title:desc">Sort: Title (Z → A)</option>
            <option value="publication_date:desc">Sort: Pub Date (Newest)</option>
            <option value="publication_date:asc">Sort: Pub Date (Oldest)</option>
          </select>
        </div>

        {hasActiveFilters && (
          <button
            type="button"
            className="iris-crawler-btn-clear-filters"
            onClick={clearFilters}
            title="Reset all filters and sort"
          >
            Reset
          </button>
        )}
      </div>

      <div className="iris-crawler-actions-group">
        <button
          type="button"
          className="iris-crawler-btn-refresh"
          onClick={onRefresh}
          title="Refresh catalogue list"
          aria-label="Refresh catalogue"
        >
          <RotateCw size={15} />
        </button>

        <button
          type="button"
          className="iris-crawler-btn-scan"
          onClick={onTriggerScan}
          disabled={isScanning}
          title={isScanning ? 'Scan in progress' : 'Scan all enabled PEC sources'}
        >
          <Play size={14} className={isScanning ? 'iris-spinner' : ''} />
          <span>{isScanning ? 'Scanning...' : 'Scan Sources'}</span>
        </button>
      </div>
    </div>
  )
}
