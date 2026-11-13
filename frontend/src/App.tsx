import { useCallback, useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, Bot, CalendarDays, Check, ChevronRight,
  Circle, Clock3, Download, FileImage, FileText, GalleryVerticalEnd, KanbanSquare,
  LayoutDashboard, MessageSquareText, Play, Plus, Power, RefreshCw, ShieldCheck, Sparkles,
  Square, Trash2, UserPlus, UsersRound, X,
} from 'lucide-react'
import { api } from './api'
import type { AgentId, Artifact, EventItem, Project, ProjectAgent, ProjectDetail, Task } from './types'

const AGENTS: Record<string, { name: string; role: string; color: string; mark: string }> = {
  pm: { name: 'Tùng', role: 'PM', color: '#263f35', mark: 'PM' },
  writer: { name: 'Sơn', role: 'Biên kịch', color: '#dd5c3d', mark: 'BK' },
  designer: { name: 'Hải', role: 'Thiết kế nhân vật', color: '#d99b2b', mark: 'TK' },
  artist: { name: 'Sáng', role: 'Họa sĩ', color: '#426b91', mark: 'HS' },
  editor: { name: 'Trí', role: 'Biên tập & dàn trang', color: '#7d5c8d', mark: 'BT' },
}

const STAGE_LABELS: Record<string, string> = {
  brief: 'Brief', planning: 'Lập kế hoạch', script: 'Kịch bản', character_design: 'Thiết kế',
  illustration: 'Minh họa', review: 'Duyệt', layout: 'Dàn trang', finalized: 'Hoàn tất', needs_attention: 'Cần xem xét',
}

const STATUS_LABELS: Record<string, string> = {
  running: 'Đang chạy tự động', queued: 'Đang chờ', stopped: 'Đã dừng', failed: 'Thất bại',
  needs_attention: 'Cần xem xét', completed: 'Hoàn tất',
}

type Tab = 'overview' | 'board' | 'schedule' | 'messages' | 'agents' | 'artifacts'

function formatTime(value: string) {
  return new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }).format(new Date(value))
}

function statusClass(status: string) { return `status status-${status.replace('_', '-')}` }

function agentInfo(id: string, agents: ProjectAgent[] = []) {
  const core = AGENTS[id]
  if (core) return core
  const custom = agents.find(agent => agent.id === id)
  return custom ? { name: custom.name, role: custom.role, color: custom.color, mark: custom.name.slice(0, 2).toUpperCase() } : undefined
}

function AgentAvatar({ id, small = false, agents = [] }: { id: string; small?: boolean; agents?: ProjectAgent[] }) {
  const agent = agentInfo(id, agents)
  if (!agent) return <div className={`avatar ${small ? 'small' : ''} system`}>AI</div>
  return <div className={`avatar ${small ? 'small' : ''}`} style={{ background: agent.color }}>{agent.mark}</div>
}

function HomePage({ projects, onCreate, onOpen }: { projects: Project[]; onCreate: () => void; onOpen: (id: string) => void }) {
  const running = projects.filter(project => ['running', 'queued'].includes(project.status)).length
  const completed = projects.filter(project => project.status === 'completed').length
  return <main className="home-page">
    <section className="home-hero">
      <div className="home-copy">
        <p className="eyebrow">AUTONOMOUS COMIC STUDIO</p>
        <h1>Một ý tưởng.<em><span>Cả xưởng</span>{' '}<span><span className="word-fix">bắt</span> tay làm.</span></em></h1>
        <p className="lede">Chỉ cần gửi một yêu cầu duy nhất. Năm agent sẽ tự lên lịch, viết, thiết kế, minh họa, duyệt và xuất PDF.</p>
        <button className="primary large" onClick={onCreate}><Sparkles size={18} /> {projects.length ? 'Tạo dự án mới' : 'Tạo truyện đầu tiên'}</button>
      </div>
      <div className="home-art" aria-hidden="true">
        <div className="panel panel-a"><span>?</span></div><div className="panel panel-b">POW!</div><div className="panel panel-c" />
      </div>
    </section>
    {projects.length > 0 && <section className="home-projects">
      <div className="home-section-head"><div><p className="eyebrow">PROJECT LIBRARY</p><h2>Dự án gần đây</h2></div><div className="home-stats"><span><b>{running}</b> đang chạy</span><span><b>{completed}</b> hoàn tất</span></div></div>
      <div className="home-project-grid">{projects.slice(0, 8).map(project => <button className="home-project-card" key={project.id} onClick={() => onOpen(project.id)}>
        <div className="home-card-top"><div className="project-thumb"><BookOpen size={17} /></div><span className={statusClass(project.status)}><i />{STATUS_LABELS[project.status] || project.status}</span></div>
        <h3>{project.title}</h3><p>{project.prompt}</p>
        <div className="home-progress"><i style={{ width: `${project.progress}%` }} /></div>
        <div className="home-card-foot"><span>{STAGE_LABELS[project.stage] || project.stage}</span><strong>{project.progress}%</strong><ArrowRight size={15} /></div>
      </button>)}</div>
    </section>}
  </main>
}

function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (p: Project) => void }) {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit() {
    if (prompt.trim().length < 12) return setError('Hãy mô tả ý tưởng rõ hơn một chút.')
    setBusy(true); setError('')
    try { onCreated(await api.create(prompt.trim())) } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tạo dự án') } finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <section className="modal">
      <button className="icon-btn close" onClick={onClose}><X size={20} /></button>
      <p className="eyebrow">NEW PRODUCTION</p>
      <h2>Bạn muốn kể chuyện gì?</h2>
      <p>Chỉ cần một lệnh. Xưởng sẽ tự quyết định các chi tiết còn thiếu và làm đến khi có PDF.</p>
      <textarea autoFocus value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Ví dụ: Truyện 8 trang cho bé 7 tuổi về một chú rái cá sợ nước, vui nhộn, bài học về lòng can đảm…" />
      <div className="prompt-meta"><span>{prompt.length}/6000</span><span>Không cần điền thêm form</span></div>
      {error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}
      <button className="primary full" disabled={busy} onClick={submit}>{busy ? <RefreshCw className="spin" size={18} /> : <Sparkles size={18} />}{busy ? 'Đang khởi động xưởng…' : 'Bắt đầu sản xuất'}<ArrowRight size={18} /></button>
    </section>
  </div>
}

function ConfirmDeleteModal({ project, busy, onClose, onConfirm }: { project: ProjectDetail; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && !busy && onClose()}>
    <section className="modal confirm-modal">
      <button className="icon-btn close" disabled={busy} onClick={onClose}><X size={20} /></button>
      <div className="danger-icon"><Trash2 size={24} /></div>
      <p className="eyebrow">DELETE PROJECT</p>
      <h2>Xóa dự án này?</h2>
      <p>“{project.title}” cùng toàn bộ ảnh, JSON và PDF sẽ bị xóa vĩnh viễn. Thao tác này không thể hoàn tác.</p>
      <div className="modal-actions">
        <button className="secondary" disabled={busy} onClick={onClose}>Giữ lại</button>
        <button className="danger-button" disabled={busy} onClick={onConfirm}>{busy ? <RefreshCw className="spin" size={17} /> : <Trash2 size={17} />} Xóa vĩnh viễn</button>
      </div>
    </section>
  </div>
}

function Sidebar({ projects, selected, onSelect, onCreate, onHome }: { projects: Project[]; selected?: string; onSelect: (id: string) => void; onCreate: () => void; onHome: () => void }) {
  return <aside className="sidebar">
    <button className="brand home-link" onClick={onHome} title="Về trang chủ"><div className="brand-mark">CF</div><div><strong>ComicFlow</strong><span>AGENT STUDIO</span></div></button>
    <button className="primary new-button" onClick={onCreate}><Plus size={17} /> Dự án mới</button>
    <div className="side-label">DỰ ÁN</div>
    <div className="project-list">{projects.map(project => <button key={project.id} className={`project-item ${selected === project.id ? 'active' : ''}`} onClick={() => onSelect(project.id)}>
      <div className="project-thumb"><BookOpen size={17} /></div>
      <div><strong>{project.title}</strong><span>{STAGE_LABELS[project.stage] || project.stage} · {project.progress}%</span></div>
      <ChevronRight size={15} />
    </button>)}</div>
    <div className="side-footer"><div className="router-dot" /><div><strong>9Router</strong><span>3 model fallback</span></div></div>
  </aside>
}

function Topbar({ project, tab, setTab, busy, onRetry, onStop, onDelete, onHome }: { project: ProjectDetail; tab: Tab; setTab: (tab: Tab) => void; busy: boolean; onRetry: () => void; onStop: () => void; onDelete: () => void; onHome: () => void }) {
  const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
    { id: 'overview', label: 'Tổng quan', icon: LayoutDashboard }, { id: 'board', label: 'Workflow', icon: KanbanSquare },
    { id: 'schedule', label: 'Lịch', icon: CalendarDays }, { id: 'messages', label: 'Giao tiếp', icon: MessageSquareText },
    { id: 'agents', label: 'Agent', icon: UsersRound },
    { id: 'artifacts', label: 'Sản phẩm', icon: GalleryVerticalEnd },
  ]
  return <><header className="topbar">
    <div className="top-title"><button className="project-home-button" onClick={onHome} title="Về trang chủ"><LayoutDashboard size={18} /></button><div><div className="crumb">DỰ ÁN <ChevronRight size={13} /> {project.id.slice(0, 8).toUpperCase()}</div><h1>{project.title}</h1></div></div>
    <div className="top-actions">
      {['failed', 'needs_attention', 'stopped'].includes(project.status) && <button className="resume-button" disabled={busy} onClick={onRetry}>{busy ? <RefreshCw className="spin" size={15} /> : <Play size={15} />} Tiếp tục</button>}
      {['running', 'queued'].includes(project.status) && <button className="stop-button" disabled={busy} onClick={onStop}>{busy ? <RefreshCw className="spin" size={15} /> : <Square size={14} fill="currentColor" />} Dừng</button>}
      {!['running', 'queued'].includes(project.status) && <button className="delete-button" disabled={busy} onClick={onDelete} title="Xóa dự án"><Trash2 size={16} /></button>}
      <div className="top-status"><span className={statusClass(project.status)}><i />{STATUS_LABELS[project.status] || project.status}</span><strong>{project.progress}%</strong></div>
    </div>
  </header><nav className="tabs">{tabs.map(item => <button className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)} key={item.id}><item.icon size={16} />{item.label}{item.id === 'messages' && project.events.length > 0 && <b>{project.events.length}</b>}</button>)}</nav></>
}

function ProgressHero({ project }: { project: ProjectDetail }) {
  const active = project.tasks.find(t => t.status === 'in_progress')
  return <section className="progress-hero">
    <div className="progress-copy"><p className="eyebrow">LIVE PRODUCTION</p><h2>{project.status === 'completed' ? 'Truyện đã sẵn sàng.' : project.status === 'stopped' ? 'Dự án đã tạm dừng.' : 'Cả xưởng đang chuyển động.'}</h2>
      <p>{project.status === 'stopped' ? 'Bạn có thể tiếp tục từ bước hiện tại hoặc xóa dự án.' : active ? `${AGENTS[active.agent]?.role} đang xử lý “${active.title}”.` : project.error || 'Workflow đang đồng bộ trạng thái.'}</p>
      <div className="progress-track"><div style={{ width: `${project.progress}%` }} /></div>
      <div className="progress-labels"><span>{STAGE_LABELS[project.stage] || project.stage}</span><span>{project.progress}%</span></div>
    </div>
    <div className="agent-orbit">{(Object.keys(AGENTS) as AgentId[]).map((id, i) => {
      const task = project.tasks.find(t => t.agent === id)
      return <div key={id} className={`orbit-agent orbit-${i} ${task?.status || 'todo'}`}><AgentAvatar id={id} small /><span>{AGENTS[id].role}</span>{task?.status === 'done' && <Check size={12} />}</div>
    })}<div className="orbit-core"><Bot size={28} /><span>LANGGRAPH</span></div></div>
  </section>
}

function AgentGrid({ tasks }: { tasks: Task[] }) {
  return <section><div className="section-title"><div><p className="eyebrow">THE CREW</p><h3>Tiến độ từng agent</h3></div><span>5 vị trí · 5 kỹ năng</span></div>
    <div className="agent-grid">{(Object.keys(AGENTS) as AgentId[]).map(id => {
      const agent = AGENTS[id]; const agentTasks = tasks.filter(t => t.agent === id); const current = agentTasks.find(t => t.status === 'in_progress') || agentTasks.at(-1)
      const done = agentTasks.filter(t => t.status === 'done').length; const pct = agentTasks.length ? Math.round(done / agentTasks.length * 100) : 0
      return <article className={`agent-card ${current?.status || 'todo'}`} key={id} style={{ '--agent': agent.color } as React.CSSProperties}>
        <div className="agent-card-head"><AgentAvatar id={id} /><span className={statusClass(current?.status || 'todo')}>{current?.status === 'in_progress' ? 'Đang làm' : current?.status === 'done' ? 'Xong' : 'Chờ'}</span></div>
        <h4>{agent.name}</h4><p>{agent.role}</p><div className="mini-progress"><i style={{ width: `${current?.status === 'in_progress' ? 64 : pct}%` }} /></div>
        <small>{current?.detail || current?.title || 'Chờ workflow giao việc'}</small>
      </article>
    })}</div>
  </section>
}

function ActivityFeed({ events, agents = [], compact = false }: { events: EventItem[]; agents?: ProjectAgent[]; compact?: boolean }) {
  const shown = compact ? events.slice(-7).reverse() : events.slice().reverse()
  return <div className={`activity-feed ${compact ? 'compact' : ''}`}>{shown.map(event => <div className="event-row" key={event.id}>
    <AgentAvatar id={event.agent} agents={agents} small /><div className="event-body"><div><strong>{agentInfo(event.agent, agents)?.role || event.agent}</strong><time>{formatTime(event.created_at)}</time></div><p>{event.message}</p><span className="event-kind">{event.event_type.replaceAll('_', ' ')}</span></div>
  </div>)}{shown.length === 0 && <div className="empty-list">Chưa có tin nhắn.</div>}</div>
}

function Overview({ project }: { project: ProjectDetail }) {
  const finished = project.tasks.filter(t => t.status === 'done').length
  return <div className="page-grid"><div className="main-col"><ProgressHero project={project} /><AgentGrid tasks={project.tasks} /></div><aside className="right-col">
    <div className="metric-grid"><div><span>WORK ITEMS</span><strong>{project.tasks.length}</strong><small>{finished} hoàn tất</small></div><div><span>ARTIFACTS</span><strong>{project.artifacts.length}</strong><small>đã tạo</small></div></div>
    <section className="side-panel"><div className="panel-head"><h3>Luồng trực tiếp</h3><Activity size={17} /></div><ActivityFeed events={project.events} agents={project.agents} compact /><button className="text-button">Xem toàn bộ giao tiếp <ArrowRight size={14} /></button></section>
    <section className="brief-card"><span>BRIEF GỐC</span><p>“{project.prompt}”</p></section>
  </aside></div>
}

const COLUMNS = [{ id: 'todo', name: 'Chờ xử lý' }, { id: 'in_progress', name: 'Đang làm' }, { id: 'done', name: 'Hoàn tất' }]
function Board({ tasks, agents }: { tasks: Task[]; agents: ProjectAgent[] }) {
  return <section className="workspace"><div className="workspace-title"><div><p className="eyebrow">WORKFLOW BOARD</p><h2>Production pipeline</h2></div><span><Circle size={9} fill="currentColor" /> Tự động assign khi có lỗi</span></div>
    <div className="kanban">{COLUMNS.map(column => <div className="kanban-column" key={column.id}><header><h3>{column.name}</h3><b>{tasks.filter(t => t.status === column.id).length}</b></header><div className="kanban-stack">{tasks.filter(t => t.status === column.id).map(task => <article className="task-card" key={task.id} style={{ '--agent': agentInfo(task.agent, agents)?.color || '#557a68' } as React.CSSProperties}>
      <div className="task-key">{task.id.toUpperCase()}</div><h4>{task.title}</h4>{task.detail && <p>{task.detail}</p>}<div className="task-foot"><div><AgentAvatar id={task.agent} agents={agents} small /><span>{agentInfo(task.agent, agents)?.role || 'Agent'}</span></div><time><Clock3 size={13} />{formatTime(task.due_at)}</time></div>
    </article>)}</div></div>)}</div>
  </section>
}

function Schedule({ tasks, agents }: { tasks: Task[]; agents: ProjectAgent[] }) {
  const sorted = [...tasks].sort((a, b) => +new Date(a.start_at) - +new Date(b.start_at)); const min = Math.min(...sorted.map(t => +new Date(t.start_at))); const max = Math.max(...sorted.map(t => +new Date(t.due_at))); const span = Math.max(1, max - min)
  return <section className="workspace"><div className="workspace-title"><div><p className="eyebrow">AUTO SCHEDULE</p><h2>Lịch sản xuất</h2></div><span><CalendarDays size={15} /> Timeline theo dependency</span></div>
    <div className="timeline"><div className="timeline-head"><span>WORK ITEM / OWNER</span><div><i>START</i><i>MIDDLE</i><i>DONE</i></div></div>{sorted.map(task => {
      const left = ((+new Date(task.start_at) - min) / span) * 86; const width = Math.max(7, ((+new Date(task.due_at) - +new Date(task.start_at)) / span) * 86)
      return <div className="timeline-row" key={task.id}><div className="timeline-label"><AgentAvatar id={task.agent} agents={agents} small /><div><strong>{task.title}</strong><span>{agentInfo(task.agent, agents)?.role || 'Agent'}</span></div></div><div className="timeline-track"><div className={`timeline-bar ${task.status}`} style={{ left: `${left + 2}%`, width: `${width}%`, background: agentInfo(task.agent, agents)?.color || '#557a68' }}><span>{task.status === 'done' ? '✓' : task.status === 'in_progress' ? 'LIVE' : ''}</span></div></div></div>
    })}</div>
  </section>
}

function Messages({ events, agents }: { events: EventItem[]; agents: ProjectAgent[] }) {
  return <section className="workspace messages"><div className="workspace-title"><div><p className="eyebrow">AGENT COMMS</p><h2>Nhật ký giao tiếp</h2></div><span><UsersRound size={15} /> {events.length} sự kiện</span></div><ActivityFeed events={events} agents={agents} /></section>
}

function AgentManagement({ project, onChanged }: { project: ProjectDetail; onChanged: () => Promise<void> }) {
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [instructions, setInstructions] = useState('')
  const [color, setColor] = useState('#557a68')
  const [busy, setBusy] = useState('')
  const [formError, setFormError] = useState('')
  const coreAgents = project.agents.filter(agent => agent.is_core)
  const customAgents = project.agents.filter(agent => !agent.is_core)

  async function createAgent() {
    if (name.trim().length < 2 || role.trim().length < 2 || instructions.trim().length < 10) {
      setFormError('Hãy nhập tên, vai trò và hướng dẫn ít nhất 10 ký tự.')
      return
    }
    setBusy('create'); setFormError('')
    try {
      await api.createAgent(project.id, { name: name.trim(), role: role.trim(), instructions: instructions.trim(), color })
      setName(''); setRole(''); setInstructions(''); setColor('#557a68'); setShowForm(false)
      await onChanged()
    } catch (error) { setFormError(error instanceof Error ? error.message : 'Không thể tạo agent') } finally { setBusy('') }
  }

  async function toggleAgent(agentId: string, enabled: boolean) {
    setBusy(agentId)
    try { await api.updateAgent(project.id, agentId, { enabled }); await onChanged() } finally { setBusy('') }
  }

  async function removeAgent(agentId: string, agentName: string) {
    if (!window.confirm(`Xóa agent “${agentName}” khỏi dự án?`)) return
    setBusy(agentId)
    try { await api.removeAgent(project.id, agentId); await onChanged() } finally { setBusy('') }
  }

  return <section className="workspace agents-workspace">
    <div className="workspace-title"><div><p className="eyebrow">PROJECT CREW</p><h2>Quản lý agent</h2></div><button className="primary add-agent-button" onClick={() => setShowForm(value => !value)}><UserPlus size={16} /> Thêm agent</button></div>
    <div className="agent-policy"><ShieldCheck size={19} /><div><strong>5 agent lõi luôn được giữ nguyên</strong><span>Agent thêm mới hoạt động như chuyên gia tư vấn và bàn giao kết quả cho toàn bộ workflow.</span></div><b>{project.agents.length} agent</b></div>
    {showForm && <div className="agent-form">
      <div className="agent-form-head"><div><p className="eyebrow">NEW SPECIALIST</p><h3>Tạo agent chuyên gia</h3></div><button className="icon-btn" onClick={() => setShowForm(false)}><X size={18} /></button></div>
      <div className="agent-form-grid"><label><span>Tên agent</span><input value={name} onChange={event => setName(event.target.value)} placeholder="Ví dụ: Mai" /></label><label><span>Vai trò</span><input value={role} onChange={event => setRole(event.target.value)} placeholder="Cố vấn văn hóa" /></label><label className="color-field"><span>Màu nhận diện</span><input type="color" value={color} onChange={event => setColor(event.target.value)} /></label></div>
      <label className="instruction-field"><span>Hướng dẫn và kỹ năng</span><textarea value={instructions} onChange={event => setInstructions(event.target.value)} placeholder="Mô tả chuyên môn, phạm vi được phép tư vấn và những điều agent phải kiểm tra…" /></label>
      {formError && <div className="form-error"><AlertTriangle size={16} />{formError}</div>}
      <div className="agent-form-actions"><button className="secondary" onClick={() => setShowForm(false)}>Hủy</button><button className="primary" disabled={busy === 'create'} onClick={createAgent}>{busy === 'create' ? <RefreshCw className="spin" size={16} /> : <UserPlus size={16} />} Tạo agent</button></div>
    </div>}
    <div className="agent-group-head"><div><h3>Đội ngũ mặc định</h3><span>{coreAgents.length} agent lõi</span></div></div>
    <div className="management-agent-grid">{coreAgents.map(agent => <article className="management-agent-card core" key={agent.id} style={{ '--agent': agent.color } as React.CSSProperties}>
      <div className="management-agent-head"><AgentAvatar id={agent.key} /><span className="core-badge"><ShieldCheck size={12} /> Mặc định</span></div><h3>{agent.name}</h3><strong>{agent.role}</strong><p>{agent.instructions}</p>
    </article>)}</div>
    <div className="agent-group-head custom-head"><div><h3>Agent bổ sung</h3><span>{customAgents.length}/10 chuyên gia</span></div></div>
    {customAgents.length > 0 ? <div className="management-agent-grid">{customAgents.map(agent => <article className={`management-agent-card custom ${agent.enabled ? '' : 'disabled'}`} key={agent.id} style={{ '--agent': agent.color } as React.CSSProperties}>
      <div className="management-agent-head"><div className="custom-agent-avatar" style={{ background: agent.color }}>{agent.name.slice(0, 2).toUpperCase()}</div><div className="agent-card-actions"><button disabled={busy === agent.id} className={`power-button ${agent.enabled ? 'enabled' : ''}`} onClick={() => toggleAgent(agent.id, !agent.enabled)} title={agent.enabled ? 'Tạm ngưng' : 'Kích hoạt'}><Power size={14} /></button><button disabled={busy === agent.id} className="remove-agent-button" onClick={() => removeAgent(agent.id, agent.name)} title="Xóa agent"><Trash2 size={14} /></button></div></div>
      <h3>{agent.name}</h3><strong>{agent.role}</strong><p>{agent.instructions}</p><span className="agent-state"><i />{agent.enabled ? 'Sẵn sàng tham gia workflow' : 'Đang tạm ngưng'}</span>
    </article>)}</div> : <div className="empty-custom-agents"><Bot size={28} /><h3>Chưa có agent bổ sung</h3><p>Thêm chuyên gia khi dự án cần kiến thức hoặc bước kiểm tra riêng.</p></div>}
  </section>
}

function artifactIcon(item: Artifact) { return item.kind.includes('image') || item.kind.includes('page') || item.kind.includes('cover') ? FileImage : item.kind === 'final_pdf' ? FileText : FileText }
function Artifacts({ artifacts }: { artifacts: Artifact[] }) {
  return <section className="workspace"><div className="workspace-title"><div><p className="eyebrow">OUTPUT LIBRARY</p><h2>Sản phẩm của xưởng</h2></div><span>{artifacts.length} tệp</span></div><div className="artifact-grid">{artifacts.map(item => {
    const Icon = artifactIcon(item); const isImage = /\.(png|jpg|jpeg|webp)$/i.test(item.url)
    return <article className="artifact-card" key={item.id}>{isImage ? <div className="artifact-preview" style={{ backgroundImage: `url(${api.artifact(item.url)})` }} /> : <div className="artifact-file"><Icon size={34} /></div>}<div className="artifact-info"><span>{item.kind.replaceAll('_', ' ')}</span><h4>{item.name}</h4><div><AgentAvatar id={item.agent} small /><a href={api.artifact(item.url)} target="_blank" rel="noreferrer"><Download size={15} /> Tải xuống</a></div></div></article>
  })}{artifacts.length === 0 && <div className="empty-artifacts"><GalleryVerticalEnd size={34} /><h3>Artifact sẽ xuất hiện ở đây</h3><p>Các agent đang chuẩn bị những file đầu tiên.</p></div>}</div></section>
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]); const [selected, setSelected] = useState<string>(); const [detail, setDetail] = useState<ProjectDetail>(); const [tab, setTab] = useState<Tab>('overview'); const [modal, setModal] = useState(false); const [deleteModal, setDeleteModal] = useState(false); const [actionBusy, setActionBusy] = useState(false); const [error, setError] = useState('')
  const refreshList = useCallback(async () => { try { const data = await api.list(); setProjects(data); setSelected(current => current && data.some(project => project.id === current) ? current : undefined) } catch (e) { setError(e instanceof Error ? e.message : 'API unavailable') } }, [])
  const refreshDetail = useCallback(async () => { if (!selected) { setDetail(undefined); return } try { setDetail(await api.get(selected)); setError('') } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tải dự án') } }, [selected])
  useEffect(() => { refreshList() }, [refreshList]); useEffect(() => { refreshDetail() }, [refreshDetail])
  useEffect(() => { if (!selected) return; const timer = window.setInterval(() => { refreshDetail(); refreshList() }, detail?.status === 'running' || detail?.status === 'queued' ? 2200 : 7000); return () => clearInterval(timer) }, [selected, detail?.status, refreshDetail, refreshList])
  function created(project: Project) { setProjects(p => [project, ...p]); setSelected(project.id); setModal(false); setTab('overview') }
  function openProject(id: string) { setSelected(id); setDetail(undefined); setTab('overview') }
  function goHome() { setSelected(undefined); setDetail(undefined); setDeleteModal(false); setTab('overview') }
  async function retryProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try { await api.retry(detail.id); await refreshDetail(); await refreshList() } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tiếp tục dự án') } finally { setActionBusy(false) }
  }
  async function stopProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try { await api.stop(detail.id); await refreshDetail(); await refreshList() } catch (e) { setError(e instanceof Error ? e.message : 'Không thể dừng dự án') } finally { setActionBusy(false) }
  }
  async function deleteProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try {
      await api.remove(detail.id)
      const remaining = projects.filter(project => project.id !== detail.id)
      setProjects(remaining); setDetail(undefined); setSelected(undefined); setDeleteModal(false); setTab('overview')
    } catch (e) { setError(e instanceof Error ? e.message : 'Không thể xóa dự án') } finally { setActionBusy(false) }
  }
  return <div className="app-shell"><Sidebar projects={projects} selected={selected} onSelect={openProject} onCreate={() => setModal(true)} onHome={goHome} /><div className="app-main">
    {error && <div className="api-error"><AlertTriangle size={16} />{error}<button onClick={() => { refreshList(); refreshDetail() }}>Thử lại</button></div>}
    {!selected ? <HomePage projects={projects} onCreate={() => setModal(true)} onOpen={openProject} /> : detail ? <><Topbar project={detail} tab={tab} setTab={setTab} busy={actionBusy} onRetry={retryProject} onStop={stopProject} onDelete={() => setDeleteModal(true)} onHome={goHome} /><div className="content">{detail.status === 'failed' && <div className="workflow-error"><AlertTriangle size={19} /><div><strong>Workflow đã dừng ở {detail.progress}%</strong><span>{detail.error || 'Agent gặp lỗi không thể tự phục hồi.'}</span></div><button disabled={actionBusy} onClick={retryProject}><Play size={15} /> Tiếp tục từ bước này</button></div>}{tab === 'overview' && <Overview project={detail} />}{tab === 'board' && <Board tasks={detail.tasks} agents={detail.agents} />}{tab === 'schedule' && <Schedule tasks={detail.tasks} agents={detail.agents} />}{tab === 'messages' && <Messages events={detail.events} agents={detail.agents} />}{tab === 'agents' && <AgentManagement project={detail} onChanged={refreshDetail} />}{tab === 'artifacts' && <Artifacts artifacts={detail.artifacts} />}</div></> : <div className="loader"><RefreshCw className="spin" /> Đang mở xưởng…</div>}
  </div>{modal && <NewProjectModal onClose={() => setModal(false)} onCreated={created} />}{deleteModal && detail && <ConfirmDeleteModal project={detail} busy={actionBusy} onClose={() => setDeleteModal(false)} onConfirm={deleteProject} />}</div>
}

