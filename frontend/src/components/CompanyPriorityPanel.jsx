import { useState } from 'react'
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor,
  useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, sortableKeyboardCoordinates, useSortable,
  verticalListSortingStrategy, arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import ScoreWeightDials from './ScoreWeightDials'
import { RENDER_API, authHeaders } from '../lib/api'

function SortableRow({ company, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: company.name })
  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 0',
        opacity: isDragging ? 0.5 : 1,
      }}
    >
      <span
        {...attributes}
        {...listeners}
        title="Drag to reorder"
        style={{ cursor: 'grab', color: '#bbb', fontSize: 16, userSelect: 'none' }}
      >⠿</span>
      <span style={{ flex: 1, fontSize: 13 }}>{company.name}</span>
      {company.status === 'pending' && (
        <span style={{ fontSize: 10, color: '#999', border: '1px solid #ddd', borderRadius: 3, padding: '1px 5px' }}>
          pending
        </span>
      )}
      <button
        onClick={() => onRemove(company.name)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#bbb', fontSize: 16, lineHeight: 1, padding: '0 2px' }}
        title="Remove"
      >×</button>
    </div>
  )
}

export default function CompanyPriorityPanel({
  companies, onCompaniesChange,
  mode, onModeChange,
  weights, onWeightsChange,
  roster = [],
  onOpenAddSearch,
}) {
  const [open, setOpen] = useState(false)
  const [dialOpen, setDialOpen] = useState(false)
  const [filing, setFiling] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return
    const oldIdx = companies.findIndex(c => c.name === active.id)
    const newIdx = companies.findIndex(c => c.name === over.id)
    onCompaniesChange(arrayMove(companies, oldIdx, newIdx))
  }

  const handleRemove = (name) => {
    onCompaniesChange(companies.filter(c => c.name !== name))
  }

  // Called from CompanyAutocomplete's "add to priority" action
  // Exposed via onOpenAddSearch which triggers the autocomplete to open
  // The actual add is handled here once the company name is known
  const addCompany = async (name) => {
    if (companies.find(c => c.name === name)) return
    const inRoster = roster.some(r => r.name.toLowerCase() === name.toLowerCase())
    const status = inRoster ? 'active' : 'pending'

    if (!inRoster) {
      const confirmed = window.confirm(`"${name}" isn't in our roster yet — request it?`)
      if (!confirmed) return
      setFiling(true)
      try {
        const res = await fetch(`${RENDER_API}/api/companies/request`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ company_name: name }),
        })
        const data = await res.json()
        if (data.issue_url) {
          window.alert(`Requested! Track it at:\n${data.issue_url}`)
        }
      } catch {
        console.error('Failed to file GitHub issue')
      } finally {
        setFiling(false)
      }
    }

    onCompaniesChange([...companies, { name, status }])
  }

  const panelStyle = {
    border: '1px solid #e0e0e0',
    borderRadius: 8,
    marginBottom: 10,
    overflow: 'hidden',
  }
  const headerStyle = {
    width: '100%', padding: '9px 12px', textAlign: 'left',
    background: 'none', border: 'none', cursor: 'pointer',
    fontWeight: 600, fontSize: 13, display: 'flex', justifyContent: 'space-between',
    alignItems: 'center',
  }
  const modeBtn = (m) => ({
    padding: '3px 11px', borderRadius: 12, border: '1px solid #ccc',
    cursor: 'pointer', fontSize: 11, fontWeight: 500,
    background: mode === m ? '#111' : '#fff',
    color: mode === m ? '#fff' : '#333',
  })

  return (
    <div style={panelStyle}>
      <button style={headerStyle} onClick={() => setOpen(o => !o)}>
        <span>Priority Companies{companies.length > 0 ? ` (${companies.length})` : ''}</span>
        <span style={{ color: '#aaa' }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={{ padding: '4px 12px 12px' }}>
          {/* Mode toggle */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <button style={modeBtn('score_boost')} onClick={() => onModeChange('score_boost')}>Score Boost</button>
            <button style={modeBtn('hard_sort')} onClick={() => onModeChange('hard_sort')}>Hard Sort</button>
          </div>

          {/* Sorted list */}
          {companies.length === 0 ? (
            <p style={{ color: '#bbb', fontSize: 12, margin: '4px 0 8px' }}>No companies yet.</p>
          ) : (
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={companies.map(c => c.name)} strategy={verticalListSortingStrategy}>
                {companies.map(c => (
                  <SortableRow key={c.name} company={c} onRemove={handleRemove} />
                ))}
              </SortableContext>
            </DndContext>
          )}

          {/* Add button */}
          <button
            onClick={onOpenAddSearch}
            disabled={filing}
            style={{ marginTop: 6, padding: '5px 12px', borderRadius: 6, border: '1px dashed #ccc', background: '#fafafa', cursor: 'pointer', fontSize: 12, color: '#555', width: '100%' }}
          >
            {filing ? 'Filing request…' : '+ Add company'}
          </button>

          {/* Weight dials */}
          <button
            onClick={() => setDialOpen(o => !o)}
            style={{ marginTop: 10, background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#888', padding: 0 }}
          >
            {dialOpen ? '▲' : '▼'} Tune score weights
          </button>
          {/* weights stored and displayed but not yet applied to scoring */}
          {dialOpen && <ScoreWeightDials weights={weights} onChange={onWeightsChange} />}
        </div>
      )}
    </div>
  )
}

// Export addCompany so App.jsx can call it when autocomplete fires "add to priority"
export { }
