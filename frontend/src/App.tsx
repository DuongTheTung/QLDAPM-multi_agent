import { useCallback, useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, Bot, CalendarDays, Check, ChevronDown, ChevronRight,
  Circle, Clock3, Download, FileImage, FileText, GalleryVerticalEnd, ListTodo,
  LayoutDashboard, LockKeyhole, MessageSquareText, Pause, Pencil, Play, Plus, Power, RefreshCw, Save,
  Search, Settings2, ShieldCheck, Sparkles, Square, Trash2, UserPlus, UsersRound, X,
} from 'lucide-react'
import { api } from './api'
import type { CreateAgentInput, RouterCatalog } from './api'
import type { AgentId, ApprovalStage, Artifact, EventContent, EventItem, Project, ProjectAgent, ProjectDetail, QualityTest, Task, WorkerRole } from './types'

const AGENTS: Record<string, { name: string; role: string; color: string; mark: string }> = {
  pm: { name: 'PM', role: 'PM', color: '#263f35', mark: 'PM' },
  writer: { name: 'Biên kịch', role: 'Biên kịch', color: '#dd5c3d', mark: 'BK' },
  designer: { name: 'Thiết kế nhân vật', role: 'Thiết kế nhân vật', color: '#d99b2b', mark: 'TK' },
  artist: { name: 'Họa sĩ', role: 'Họa sĩ', color: '#426b91', mark: 'HS' },
  reviewer: { name: 'Kiểm duyệt', role: 'Kiểm duyệt', color: '#3f8178', mark: 'KD' },
  editor: { name: 'Biên tập & dàn trang', role: 'Biên tập & dàn trang', color: '#7d5c8d', mark: 'BT' },
}

const DEFAULT_TEXT_MODELS = ['cx/gpt-5.6-sol', 'ag/gemini-3.8-flash-medium', 'gc/gemini-3-pro-preview']
const WORKER_ROLES: { key: WorkerRole; label: string; help: string }[] = [
  { key: 'writer', label: 'Biên kịch', help: 'Đề xuất cảnh và đoạn kể để Biên kịch chính tổng hợp.' },
  { key: 'designer', label: 'Thiết kế nhân vật', help: 'Chia ảnh tham chiếu nhân vật và bối cảnh.' },
  { key: 'artist', label: 'Họa sĩ', help: 'Nhận các trang riêng và tạo ảnh song parallel.' },
  { key: 'reviewer', label: 'Kiểm duyệt', help: 'Chia các sản phẩm Testing để kiểm tra.' },
  { key: 'editor', label: 'Biên tập & dàn trang', help: 'Chia các trang cần ghép tranh và chữ.' },
]
const ROLE_COLORS: Record<WorkerRole, string> = {
  writer: '#dd5c3d', designer: '#d99b2b', artist: '#426b91',
  reviewer: '#3f8178', editor: '#7d5c8d',
}

const STAGE_LABELS: Record<string, string> = {
  brief: 'Brief', planning: 'Lập kế hoạch', script: 'Kịch bản', character_design: 'Thiết kế',
  illustration: 'Minh họa', testing: 'Testing', review: 'Kiểm duyệt', layout: 'Dàn trang', finalized: 'Hoàn tất', needs_attention: 'Cần xem xét',
}

const STATUS_LABELS: Record<string, string> = {
  running: 'Đang chạy tự động', queued: 'Đang chờ', stopped: 'Đã dừng', failed: 'Thất bại',
  needs_attention: 'Cần xem xét', completed: 'Hoàn tất', paused: 'Đã tạm dừng',
  pause_requested: 'Đang chờ tạm dừng', awaiting_approval: 'Đang chờ bạn duyệt',
}

type Tab = 'overview' | 'list' | 'schedule' | 'messages' | 'agents' | 'artifacts'
type SystemPage = 'home' | 'models'

const PROJECT_TABS: Tab[] = ['overview', 'list', 'schedule', 'messages', 'agents', 'artifacts']

function readRoute(): { page: SystemPage; projectId?: string; tab: Tab } {
  const parts = window.location.pathname.split('/').filter(Boolean)
  if (parts[0] === 'models') return { page: 'models', tab: 'overview' }
  if (parts[0] === 'projects' && parts[1]) {
    const requested = parts[2] as Tab
    return {
      page: 'home', projectId: decodeURIComponent(parts[1]),
      tab: PROJECT_TABS.includes(requested) ? requested : 'overview',
    }
  }
  return { page: 'home', tab: 'overview' }
}

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

function agentLabel(id: string, agents: ProjectAgent[] = []) {
  const agent = agentInfo(id, agents)
  return agent ? `${agent.name} · ${agent.role}` : id
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
        <p className="lede">Chỉ cần gửi một yêu cầu duy nhất. Sáu agent sẽ tự lên lịch, viết, thiết kế, minh họa, duyệt và xuất PDF.</p>
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
  const [agents, setAgents] = useState<CreateAgentInput[]>([])
  const [showAgentForm, setShowAgentForm] = useState(false)
  const [agentName, setAgentName] = useState('')
  const [agentRole, setAgentRole] = useState<WorkerRole>('writer')
  const [agentInstructions, setAgentInstructions] = useState('')
  const [agentModel, setAgentModel] = useState('')
  const [agentImageModel, setAgentImageModel] = useState('')
  const [coreModels, setCoreModels] = useState<Partial<Record<AgentId, string>>>({})
  const [modelOptions, setModelOptions] = useState(DEFAULT_TEXT_MODELS)
  const [imageOptions, setImageOptions] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api.models().then(catalog => {
      setModelOptions(catalog.models.length ? catalog.models : DEFAULT_TEXT_MODELS)
      setImageOptions(catalog.image_model ? [catalog.image_model] : [])
    }).catch(() => setModelOptions(DEFAULT_TEXT_MODELS))
  }, [])
  function addAgent() {
    if (agentName.trim().length < 2 || agentInstructions.trim().length < 10) {
      setError('Agent bổ sung cần có tên và hướng dẫn ít nhất 10 ký tự.'); return
    }
    if (agents.length >= 10) return setError('Mỗi dự án được thêm tối đa 10 agent.')
    setAgents(items => [...items, {
      name: agentName.trim(), role_key: agentRole, instructions: agentInstructions.trim(),
      color: ROLE_COLORS[agentRole], model: agentModel || null, fallback_models: [],
      image_model: ['designer', 'artist'].includes(agentRole) ? agentImageModel || null : null,
    }])
    setAgentName(''); setAgentRole('writer'); setAgentInstructions(''); setAgentModel('')
    setAgentImageModel(''); setShowAgentForm(false); setError('')
  }
  async function submit() {
    if (prompt.trim().length < 12) return setError('Hãy mô tả ý tưởng rõ hơn một chút.')
    setBusy(true); setError('')
    const coreAgentModels = (Object.keys(coreModels) as AgentId[])
      .filter(agentId => Boolean(coreModels[agentId]))
      .map(agentId => ({ agent_id: agentId, model: coreModels[agentId] }))
    try { onCreated(await api.create(prompt.trim(), agents, coreAgentModels)) } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tạo dự án') } finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <section className="modal project-modal">
      <button className="icon-btn close" onClick={onClose}><X size={20} /></button>
      <p className="eyebrow">NEW PRODUCTION</p>
      <h2>Bạn muốn kể chuyện gì?</h2>
      <p>Chỉ cần một lệnh. Xưởng sẽ tự quyết định các chi tiết còn thiếu và làm đến khi có PDF.</p>
      <textarea autoFocus value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Ví dụ: Truyện 8 trang cho bé 7 tuổi về một chú rái cá sợ nước, vui nhộn, bài học về lòng can đảm…" />
      <div className="prompt-meta"><span>{prompt.length}/6000</span><span>Không cần điền thêm form</span></div>
      <div className="project-crew-picker">
        <div className="crew-picker-head"><div><strong>Đội agent của dự án</strong><span>6 agent mặc định luôn được sử dụng</span></div><button className="secondary" disabled={agents.length >= 10} onClick={() => setShowAgentForm(value => !value)}><UserPlus size={14} /> Thêm agent</button></div>
        <div className="default-crew-row">{(Object.keys(AGENTS) as AgentId[]).map(id => <span key={id}><span><Check size={11} />{AGENTS[id].name} · {AGENTS[id].role}</span><select aria-label={`Model của ${AGENTS[id].name}`} value={coreModels[id] || ''} onChange={event => setCoreModels(current => ({ ...current, [id]: event.target.value }))}><option value="">Model mặc định ({modelOptions[0]})</option>{modelOptions.map(model => <option key={model} value={model}>{model}</option>)}</select></span>)}</div>
        {agents.length > 0 && <div className="draft-agent-list">{agents.map((agent, index) => <div key={`${agent.name}-${index}`}><span style={{ background: agent.color }}>{agent.name.slice(0, 2).toUpperCase()}</span><div><strong>{agent.name}</strong><small>{WORKER_ROLES.find(item => item.key === agent.role_key)?.label} · {agent.model || 'Model mặc định'}</small></div><button disabled={busy} onClick={() => setAgents(items => items.filter((_, itemIndex) => itemIndex !== index))}><X size={13} /></button></div>)}</div>}
        {showAgentForm && <div className="project-agent-form"><input value={agentName} onChange={event => setAgentName(event.target.value)} placeholder="Tên agent" /><select value={agentRole} onChange={event => { setAgentRole(event.target.value as WorkerRole); setAgentImageModel('') }}>{WORKER_ROLES.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select><select aria-label="Model chính" value={agentModel} onChange={event => setAgentModel(event.target.value)}><option value="">Model mặc định ({modelOptions[0]})</option>{modelOptions.map(model => <option key={model} value={model}>{model}</option>)}</select>{['designer', 'artist'].includes(agentRole) && <select aria-label="Model tạo ảnh" value={agentImageModel} onChange={event => setAgentImageModel(event.target.value)}><option value="">Model ảnh mặc định{imageOptions[0] ? ` (${imageOptions[0]})` : ''}</option>{imageOptions.map(model => <option key={model} value={model}>{model}</option>)}</select>}<textarea value={agentInstructions} onChange={event => setAgentInstructions(event.target.value)} placeholder="Hướng dẫn và kỹ năng của agent…" /><div><button className="secondary" onClick={() => setShowAgentForm(false)}>Hủy</button><button className="primary" onClick={addAgent}>Thêm vào dự án</button></div></div>}
      </div>
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

function Sidebar({ projects, selected, systemPage, onSelect, onCreate, onHome, onModels }: { projects: Project[]; selected?: string; systemPage: SystemPage; onSelect: (id: string) => void; onCreate: () => void; onHome: () => void; onModels: () => void }) {
  return <aside className="sidebar">
    <button className="brand home-link" onClick={onHome} title="Về trang chủ"><div className="brand-mark">CF</div><div><strong>ComicFlow</strong><span>AGENT STUDIO</span></div></button>
    <button className="primary new-button" onClick={onCreate}><Plus size={17} /> Dự án mới</button>
    <div className="side-label">HỆ THỐNG</div>
    <button className={`system-nav ${systemPage === 'models' ? 'active' : ''}`} onClick={onModels}><Settings2 size={17} /><span><strong>Model 9Router</strong><small>Cấu hình mặc định</small></span><ChevronRight size={14} /></button>
    <div className="side-label">DỰ ÁN</div>
    <div className="project-list">{projects.map(project => <button key={project.id} className={`project-item ${selected === project.id ? 'active' : ''}`} onClick={() => onSelect(project.id)}>
      <div className="project-thumb"><BookOpen size={17} /></div>
      <div><strong>{project.title}</strong><span>{STAGE_LABELS[project.stage] || project.stage} · {project.progress}%</span></div>
      <ChevronRight size={15} />
    </button>)}</div>
    <button className="side-footer" onClick={onModels}><div className="router-dot" /><div><strong>9Router</strong><span>Quản lý model</span></div></button>
  </aside>
}

function Topbar({ project, tab, setTab, busy, onRetry, onPause, onResume, onStop, onDelete, onHome }: { project: ProjectDetail; tab: Tab; setTab: (tab: Tab) => void; busy: boolean; onRetry: () => void; onPause: () => void; onResume: () => void; onStop: () => void; onDelete: () => void; onHome: () => void }) {
  const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
    { id: 'overview', label: 'Tổng quan', icon: LayoutDashboard }, { id: 'list', label: 'List', icon: ListTodo },
    { id: 'schedule', label: 'Lịch', icon: CalendarDays }, { id: 'messages', label: 'Giao tiếp', icon: MessageSquareText },
    { id: 'agents', label: 'Agent', icon: UsersRound },
    { id: 'artifacts', label: 'Sản phẩm', icon: GalleryVerticalEnd },
  ]
  return <><header className="topbar">
    <div className="top-title"><button className="project-home-button" onClick={onHome} title="Về trang chủ"><LayoutDashboard size={18} /></button><div><div className="crumb">DỰ ÁN <ChevronRight size={13} /> {project.id.slice(0, 8).toUpperCase()}</div><h1>{project.title}</h1></div></div>
    <div className="top-actions">
      {['failed', 'needs_attention', 'stopped'].includes(project.status) && <button className="resume-button" disabled={busy} onClick={onRetry}>{busy ? <RefreshCw className="spin" size={15} /> : <Play size={15} />} Tiếp tục</button>}
      {project.status === 'paused' && <button className="resume-button" disabled={busy} onClick={onResume}><Play size={15} /> Tiếp tục</button>}
      {['running', 'queued'].includes(project.status) && <button className="pause-button" disabled={busy} onClick={onPause}>{busy ? <RefreshCw className="spin" size={15} /> : <Pause size={14} fill="currentColor" />} Tạm dừng</button>}
      {project.status === 'pause_requested' && <button className="pause-button" disabled><RefreshCw className="spin" size={15} /> Đang dừng an toàn</button>}
      {['running', 'queued', 'pause_requested'].includes(project.status) && <button className="stop-button" disabled={busy} onClick={onStop} title="Dừng hẳn dự án"><Square size={13} fill="currentColor" /> Dừng hẳn</button>}
      {!['running', 'queued', 'pause_requested'].includes(project.status) && <button className="delete-button" disabled={busy} onClick={onDelete} title="Xóa dự án"><Trash2 size={16} /></button>}
      <div className="top-status"><span className={statusClass(project.status)}><i />{STATUS_LABELS[project.status] || project.status}</span><strong>{project.progress}%</strong></div>
    </div>
  </header><nav className="tabs">{tabs.map(item => <button className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)} key={item.id}><item.icon size={16} />{item.label}{item.id === 'messages' && project.events.length > 0 && <b>{project.events.length}</b>}</button>)}</nav></>
}

function ProgressHero({ project }: { project: ProjectDetail }) {
  const active = project.tasks.find(t => t.status === 'in_progress' && t.item_type === 'subtask') || project.tasks.find(t => t.status === 'in_progress')
  const orbitPoints: Record<AgentId | 'core', { x: number; y: number }> = {
    pm: { x: 60, y: 42 }, writer: { x: 180, y: 27 }, designer: { x: 294, y: 65 },
    artist: { x: 300, y: 174 }, reviewer: { x: 245, y: 211 }, editor: { x: 90, y: 210 },
    core: { x: 180, y: 117 },
  }
  function orbitRole(value: unknown): AgentId | 'core' | undefined {
    if (value === 'user' || value === 'system' || value === 'langgraph') return 'core'
    if (typeof value !== 'string') return undefined
    if (value in AGENTS) return value as AgentId
    return project.agents.find(agent => agent.id === value)?.role_key
  }
  type OrbitConnection = { id: number; from: AgentId | 'core'; to: AgentId | 'core'; revision: boolean; active: boolean }
  const connectionMap = new Map<string, OrbitConnection>()
  project.events.slice(-30).forEach(event => {
    if (event.event_type === 'testing_started') return
    let from = orbitRole(event.agent)
    let to = orbitRole(event.payload.to ?? event.payload.assigned_to)
    if (!from || !to || from === to) return
    const key = `${from}:${to}`
    connectionMap.delete(key)
    connectionMap.set(key, {
      id: event.id, from, to,
      revision: event.event_type.includes('revision') || event.event_type === 'testing_failed',
      active: false,
    })
  })
  const activeTests = project.quality_tests.filter(test => test.status === 'testing')
  activeTests.forEach(test => {
    const from = orbitRole(test.owner_agent); const to = orbitRole(test.reviewer_agent)
    if (!from || !to || from === to) return
    const key = `${from}:${to}`
    connectionMap.delete(key)
    connectionMap.set(key, { id: -test.id, from, to, revision: false, active: true })
  })
  const connections = [...connectionMap.values()].slice(-5)
  function connectionPath(connection: OrbitConnection) {
    const start = orbitPoints[connection.from]; const end = orbitPoints[connection.to]
    if (connection.from === 'core' || connection.to === 'core') return `M ${start.x} ${start.y} L ${end.x} ${end.y}`
    const middleX = (start.x + end.x) / 2; const middleY = (start.y + end.y) / 2
    const radialX = middleX - orbitPoints.core.x; const radialY = middleY - orbitPoints.core.y
    const radialLength = Math.hypot(radialX, radialY) || 1
    const bend = connection.revision ? 28 : 18
    const controlX = middleX + radialX / radialLength * bend
    const controlY = middleY + radialY / radialLength * bend
    return `M ${start.x} ${start.y} Q ${controlX.toFixed(1)} ${controlY.toFixed(1)} ${end.x} ${end.y}`
  }
  const reviewerActive = activeTests.length > 0
  return <section className="progress-hero">
    <div className="progress-copy"><p className="eyebrow">LIVE PRODUCTION</p><h2>{project.status === 'completed' ? 'Truyện đã sẵn sàng.' : project.status === 'stopped' ? 'Dự án đã tạm dừng.' : 'Cả xưởng đang chuyển động.'}</h2>
      <p>{project.status === 'stopped' ? 'Bạn có thể tiếp tục từ bước hiện tại hoặc xóa dự án.' : active ? `${agentLabel(active.agent, project.agents)} đang xử lý “${active.title}”.` : project.error || 'List đang đồng bộ trạng thái.'}</p>
      <div className="progress-track"><div style={{ width: `${project.progress}%` }} /></div>
      <div className="progress-labels"><span>{STAGE_LABELS[project.stage] || project.stage}</span><span>{project.progress}%</span></div>
    </div>
    <div className="agent-orbit"><svg className="communication-lines" viewBox="0 0 360 235" aria-hidden="true">{connections.map((connection, index) => {
      const path = connectionPath(connection)
      return <g key={connection.id} className={`${connection.revision ? 'revision-link' : 'handoff-link'} ${connection.active ? 'active-link' : ''}`}><path d={path} /><circle className="message-particle" r={connection.active ? 3.4 : 2.7}><animateMotion dur={`${1.1 + index * 0.07}s`} repeatCount="indefinite" path={path} /></circle></g>
    })}</svg>{(Object.keys(AGENTS) as AgentId[]).map(id => {
      const agentTasks = project.tasks.filter(t => t.agent === id)
      const task = agentTasks.find(t => t.status === 'in_progress') || agentTasks.find(t => t.status === 'testing') || agentTasks.at(-1)
      const visualStatus = id === 'reviewer' && reviewerActive ? 'testing' : task?.status || 'todo'
      const point = orbitPoints[id]
      return <div key={id} className={`orbit-agent ${visualStatus}`} style={{ left: `${point.x / 3.6}%`, top: `${point.y / 2.35}%` }}><AgentAvatar id={id} small /><span>{AGENTS[id].role}</span>{visualStatus === 'done' && <Check size={12} />}</div>
    })}<div className="orbit-core"><Bot size={28} /><span>LANGGRAPH</span></div></div>
  </section>
}

function AgentGrid({ tasks, agents, qualityTests }: { tasks: Task[]; agents: ProjectAgent[]; qualityTests: QualityTest[] }) {
  const crew = agents.filter(agent => agent.enabled)
  return <section><div className="section-title"><div><p className="eyebrow">THE CREW</p><h3>Tiến độ từng agent</h3></div><span>{crew.length} agent · quản lý theo tên và vai trò</span></div>
    <div className="agent-grid">{crew.map(agent => {
      const id = agent.is_core ? agent.key : agent.id; const agentTasks = tasks.filter(t => t.agent === id); const current = agentTasks.find(t => t.status === 'in_progress' && t.item_type === 'subtask') || agentTasks.find(t => t.status === 'testing') || agentTasks.find(t => t.status === 'in_progress') || agentTasks.at(-1)
      const done = agentTasks.filter(t => t.status === 'done').length; const pct = agentTasks.length ? Math.round(done / agentTasks.length * 100) : 0
      const reviewerTests = qualityTests.filter(test => test.reviewer_agent === id)
      const activeReviews = reviewerTests.filter(test => test.status === 'testing')
      const completedReviews = reviewerTests.filter(test => test.status === 'completed').length
      const isReviewing = activeReviews.length > 0
      const reviewPct = reviewerTests.length ? Math.round((completedReviews + activeReviews.length * 0.5) / reviewerTests.length * 100) : 0
      const visualStatus = isReviewing ? 'testing' : current?.status || 'todo'
      const progress = reviewerTests.length ? reviewPct : current?.status === 'in_progress' ? 64 : pct
      const detail = isReviewing
        ? `Đang kiểm tra “${activeReviews.at(-1)?.title}” · ${completedReviews}/${reviewerTests.length} đầu ra đã duyệt`
        : reviewerTests.length ? `${completedReviews}/${reviewerTests.length} đầu ra đã kiểm duyệt` : current?.detail || current?.title || 'Chờ PM giao task'
      return <article className={`agent-card ${visualStatus}`} key={agent.id} style={{ '--agent': agent.color } as React.CSSProperties}>
        <div className="agent-card-head"><AgentAvatar id={id} agents={agents} /><span className={statusClass(visualStatus)}>{visualStatus === 'in_progress' ? 'Đang làm' : visualStatus === 'testing' ? 'Đang kiểm duyệt' : visualStatus === 'done' ? 'Xong' : 'Chờ'}</span></div>
        <h4>{agent.name}</h4><p>{agent.role}</p><div className="mini-progress"><i style={{ width: `${progress}%` }} /></div>
        <small>{detail}</small>
      </article>
    })}</div>
  </section>
}

function ActivityFeed({ events, agents = [], compact = false }: { events: EventItem[]; agents?: ProjectAgent[]; compact?: boolean }) {
  const shown = compact ? events.slice(-7).reverse() : events.slice().reverse()
  return <div className={`activity-feed ${compact ? 'compact' : ''}`}>{shown.map(event => <div className="event-row" key={event.id}>
    <AgentAvatar id={event.agent} agents={agents} small /><div className="event-body"><div><strong>{agentLabel(event.agent, agents)}</strong><time>{formatTime(event.created_at)}</time></div><p>{event.message}</p><span className="event-kind">{event.event_type.replaceAll('_', ' ')}</span></div>
  </div>)}{shown.length === 0 && <div className="empty-list">Chưa có tin nhắn.</div>}</div>
}

function Overview({ project }: { project: ProjectDetail }) {
  const finished = project.tasks.filter(t => t.status === 'done').length
  return <div className="page-grid"><div className="main-col"><ProgressHero project={project} /><AgentGrid tasks={project.tasks} agents={project.agents} qualityTests={project.quality_tests} /></div><aside className="right-col">
    <div className="metric-grid"><div><span>WORK ITEMS</span><strong>{project.tasks.length}</strong><small>{finished} hoàn tất</small></div><div><span>ARTIFACTS</span><strong>{project.artifacts.length}</strong><small>đã tạo</small></div></div>
    <section className="side-panel"><div className="panel-head"><h3>Luồng trực tiếp</h3><Activity size={17} /></div><ActivityFeed events={project.events} agents={project.agents} compact /><button className="text-button">Xem toàn bộ giao tiếp <ArrowRight size={14} /></button></section>
    <section className="brief-card"><span>BRIEF GỐC</span><p>“{project.prompt}”</p></section>
  </aside></div>
}

type WorkState = 'todo' | 'in_progress' | 'testing' | 'review' | 'blocked' | 'done'

const WORK_STATE_LABELS: Record<WorkState, string> = {
  todo: 'Sẵn sàng', in_progress: 'Đang làm', testing: 'Testing', review: 'Chờ duyệt', blocked: 'Bị chặn', done: 'Hoàn tất',
}

function taskStatusLabel(status: string) {
  return WORK_STATE_LABELS[status as WorkState] || status
}

function TaskList({ project }: { project: ProjectDetail }) {
  const { tasks, agents } = project
  const [filter, setFilter] = useState<'all' | WorkState>('all')
  const [search, setSearch] = useState('')
  const roots = tasks.filter(task => !task.parent_id)
  const subtasks = tasks.filter(task => task.parent_id)
  const byId = new Map(tasks.map(task => [task.id, task]))
  const pendingApproval = project.approvals.find(item => item.status === 'pending')
  const approvalAgent = pendingApproval ? ({ script: 'writer', character_design: 'designer', illustration: 'artist', final: 'editor' } as Record<string, string>)[pendingApproval.stage] : ''

  function workState(task: Task): WorkState {
    if (!task.parent_id && task.status === 'done' && approvalAgent === task.agent) return 'review'
    if (task.status === 'done') return 'done'
    if (task.status === 'testing') return 'testing'
    if (task.status === 'in_progress') return 'in_progress'
    if (task.depends_on.some(id => byId.get(id)?.status !== 'done')) return 'blocked'
    return 'todo'
  }

  const counts = (['todo', 'in_progress', 'testing', 'review', 'blocked', 'done'] as WorkState[]).reduce((result, state) => ({ ...result, [state]: roots.filter(task => workState(task) === state).length }), {} as Record<WorkState, number>)
  const normalizedSearch = search.trim().toLocaleLowerCase('vi')
  const visibleRoots = roots.filter(task => {
    const children = subtasks.filter(item => item.parent_id === task.id)
    const matchesText = !normalizedSearch || [task.title, task.detail, agentLabel(task.agent, agents), ...children.flatMap(item => [item.title, item.detail, agentLabel(item.agent, agents)])].some(value => value?.toLocaleLowerCase('vi').includes(normalizedSearch))
    return matchesText && (filter === 'all' || workState(task) === filter)
  })
  const finished = subtasks.filter(task => task.status === 'done').length
  const groups = (['in_progress', 'testing', 'review', 'todo', 'blocked', 'done'] as WorkState[]).map(state => ({ state, tasks: visibleRoots.filter(task => workState(task) === state) })).filter(group => group.tasks.length > 0)

  return <section className="workspace task-list-workspace">
    <div className="workspace-title"><div><p className="eyebrow">LIST + WORKFLOW</p><h2>Danh sách công việc sản xuất</h2></div><span><Check size={13} /> {finished}/{subtasks.length} subtask hoàn tất</span></div>
    <div className="workflow-pipeline"><div className="pipeline-head"><div><strong>Luồng sản xuất</strong><span>PM tự động điều phối theo dependency</span></div><span className={statusClass(project.status)}><i />{STATUS_LABELS[project.status] || project.status}</span></div><div className="pipeline-track">{roots.map((task, index) => {
      const state = workState(task)
      return <div className="pipeline-unit" key={task.id}>{index > 0 && <i className={`pipeline-link ${state}`} />}<button className={`pipeline-node ${state}`} onClick={() => setFilter(state)} title={task.title}><span>{task.status === 'done' && state !== 'review' ? <Check size={13} /> : state === 'in_progress' ? <RefreshCw className="spin" size={12} /> : state === 'review' ? <ShieldCheck size={13} /> : <Circle size={10} />}</span><div><strong>{agentInfo(task.agent, agents)?.role || task.agent}</strong><small>{taskStatusLabel(state)}</small></div></button></div>
    })}</div></div>
    <div className="list-toolbar"><label><Search size={15} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Tìm task, subtask hoặc agent…" /></label><div className="state-filters"><button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>Tất cả <b>{roots.length}</b></button>{(['todo', 'in_progress', 'testing', 'review', 'blocked', 'done'] as WorkState[]).map(state => <button className={filter === state ? `active ${state}` : state} onClick={() => setFilter(state)} key={state}>{WORK_STATE_LABELS[state]} <b>{counts[state]}</b></button>)}</div></div>
    <div className="task-list-head"><span>Công việc / người phụ trách</span><span>Trạng thái</span><span>Thời hạn</span></div>
    <div className="workflow-list-groups">{groups.map(group => <section className={`workflow-state-group ${group.state}`} key={group.state}><header><div><i /><strong>{WORK_STATE_LABELS[group.state]}</strong><b>{group.tasks.length}</b></div><span>{group.state === 'blocked' ? 'Đang chờ task phụ thuộc' : group.state === 'review' ? 'Chờ quyết định của bạn' : ''}</span></header><div className="task-list-groups">{group.tasks.map(task => {
      const state = workState(task)
      const children = subtasks.filter(item => item.parent_id === task.id)
      return <article className={`task-list-group ${state}`} key={task.id} style={{ '--agent': agentInfo(task.agent, agents)?.color || '#557a68' } as React.CSSProperties}>
        <div className="task-main-row">
          <div className="task-main-info"><AgentAvatar id={task.agent} agents={agents} /><div><span className="task-key">{task.id.toUpperCase()}</span><h3>{task.title}</h3><p>{task.detail}</p><small>{agentLabel(task.agent, agents)} · {children.length} subtask{task.depends_on.length > 0 ? ` · Phụ thuộc ${task.depends_on.join(', ')}` : ''}</small></div></div>
          <span className={statusClass(state)}><i />{taskStatusLabel(state)}</span>
          <time><Clock3 size={13} />{formatTime(task.due_at)}</time>
        </div>
        {children.length > 0 && <div className="subtask-list">{children.map((child, index) => {
          const childState = workState(child)
          return <div className={`subtask-row ${childState}`} key={child.id}><div className="subtask-tree"><i />{childState === 'done' ? <Check size={14} /> : childState === 'in_progress' ? <RefreshCw className="spin" size={13} /> : childState === 'blocked' ? <LockKeyhole size={12} /> : <Circle size={12} />}<AgentAvatar id={child.agent} agents={agents} small /><div><span>SUBTASK {String(index + 1).padStart(2, '0')} · {agentLabel(child.agent, agents)}</span><strong>{child.title}</strong><small>{child.detail}</small></div></div><span className={statusClass(childState)}><i />{taskStatusLabel(childState)}</span><time>{formatTime(child.due_at)}</time></div>
        })}</div>}
      </article>
    })}</div></section>)}{visibleRoots.length === 0 && <div className="empty-list">Không có công việc phù hợp bộ lọc.</div>}</div>
  </section>
}

function Schedule({ tasks, agents }: { tasks: Task[]; agents: ProjectAgent[] }) {
  const sorted = [...tasks].sort((a, b) => +new Date(a.start_at) - +new Date(b.start_at)); const min = Math.min(...sorted.map(t => +new Date(t.start_at))); const max = Math.max(...sorted.map(t => +new Date(t.due_at))); const span = Math.max(1, max - min)
  return <section className="workspace"><div className="workspace-title"><div><p className="eyebrow">AUTO SCHEDULE</p><h2>Lịch sản xuất</h2></div><span><CalendarDays size={15} /> Timeline theo dependency</span></div>
    <div className="timeline"><div className="timeline-head"><span>WORK ITEM / OWNER</span><div><i>START</i><i>MIDDLE</i><i>DONE</i></div></div>{sorted.map(task => {
      const left = ((+new Date(task.start_at) - min) / span) * 86; const width = Math.max(7, ((+new Date(task.due_at) - +new Date(task.start_at)) / span) * 86)
      return <div className="timeline-row" key={task.id}><div className="timeline-label"><AgentAvatar id={task.agent} agents={agents} small /><div><strong>{task.title}</strong><span>{agentLabel(task.agent, agents)}</span></div></div><div className="timeline-track"><div className={`timeline-bar ${task.status}`} style={{ left: `${left + 2}%`, width: `${width}%`, background: agentInfo(task.agent, agents)?.color || '#557a68' }}><span>{task.status === 'done' ? '✓' : task.status === 'in_progress' ? 'LIVE' : ''}</span></div></div></div>
    })}</div>
  </section>
}

const APPROVAL_LABELS: Record<ApprovalStage, string> = {
  script: 'Kịch bản', character_design: 'Thiết kế nhân vật', illustration: 'Minh họa', final: 'PDF cuối',
}

const CONTENT_LABELS: Record<string, string> = {
  plan: 'Kế hoạch sản xuất', script: 'Kịch bản', character_bible: 'Hồ sơ nhân vật',
  page_prompts: 'Mô tả minh họa', review: 'Kết quả biên tập',
  title: 'Tên truyện', audience_age: 'Độ tuổi', language: 'Ngôn ngữ', page_count: 'Số trang',
  genre: 'Thể loại', tone: 'Không khí', safety_notes: 'Lưu ý an toàn',
  acceptance_criteria: 'Tiêu chí hoàn thành', visual_format: 'Định dạng tranh', logline: 'Tóm tắt truyện',
  theme: 'Chủ đề', lesson: 'Bài học', structure: 'Cấu trúc câu chuyện', opening: 'Mở đầu',
  rising_action: 'Thắt nút', climax: 'Cao trào', ending: 'Kết thúc', characters: 'Nhân vật',
  pages: 'Nội dung từng trang', page_number: 'Trang', beat: 'Nhịp truyện', setting: 'Bối cảnh',
  action: 'Hành động', emotion: 'Cảm xúc', characters_present: 'Nhân vật trong tranh', story_text: 'Đoạn kể trên trang',
  dialogues: 'Lời nhân vật trong đoạn kể', speaker: 'Người nói', text: 'Nội dung',
  caption: 'Lời dẫn cũ', role: 'Vai trò', age_or_type: 'Tuổi hoặc loài', traits: 'Tính cách',
  style_lock: 'Phong cách tranh đã khóa', negative_lock: 'Những điều phải tránh', profile: 'Hồ sơ',
  fixed_anchor: 'Mô tả cố định', reference_prompt: 'Mô tả ảnh tham chiếu', settings: 'Bối cảnh cố định',
  cover: 'Bìa truyện', prompt: 'Mô tả tạo ảnh', title_area: 'Vùng đặt tên truyện',
  composition_note: 'Lưu ý bố cục tranh', continuity_note: 'Lưu ý nhất quán', verdict: 'Kết luận',
  summary: 'Tóm tắt đánh giá', serious_issues: 'Lỗi nghiêm trọng', minor_notes: 'Ghi chú nhỏ',
  revision_agent: 'Agent cần sửa', revision_instructions: 'Yêu cầu sửa', scores: 'Điểm đánh giá',
  category: 'Nhóm lỗi', reason: 'Lý do', evidence: 'Bằng chứng', story: 'Cốt truyện',
  age_safety: 'An toàn theo tuổi', consistency: 'Độ nhất quán', script_fidelity: 'Bám sát kịch bản',
  recommendations: 'Khuyến nghị', risks: 'Rủi ro', handoff_note: 'Ghi chú bàn giao',
}

function isContentObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fieldLabel(key: string) {
  return CONTENT_LABELS[key] || key.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase())
}

function itemTitle(item: Record<string, unknown>, index: number) {
  if (item.page_number != null) return `Trang ${String(item.page_number)}`
  if (item.name) return String(item.name)
  if (item.speaker) return String(item.speaker)
  if (item.category) return String(item.category)
  return `Mục ${index + 1}`
}

function HumanContentValue({ value, fieldKey = '', depth = 0 }: { value: unknown; fieldKey?: string; depth?: number }) {
  if (value == null || value === '') return <span className="empty-value">Chưa có nội dung</span>
  if (typeof value === 'boolean') return <span>{value ? 'Có' : 'Không'}</span>
  if (typeof value === 'string' || typeof value === 'number') return <p>{String(value)}</p>
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="empty-value">Chưa có nội dung</span>
    if (value.every(item => !isContentObject(item) && !Array.isArray(item))) {
      return <ul className="human-bullets">{value.map((item, index) => <li key={index}>{String(item)}</li>)}</ul>
    }
    return <div className={`human-card-list ${fieldKey === 'pages' ? 'page-list' : ''}`}>{value.map((item, index) => isContentObject(item) ? <article className="human-card" key={index}><h5>{itemTitle(item, index)}</h5><HumanContentValue value={item} depth={depth + 1} /></article> : <div key={index}><HumanContentValue value={item} depth={depth + 1} /></div>)}</div>
  }
  if (isContentObject(value)) {
    const entries = Object.entries(value).filter(([key]) =>
      !['trace', 'page_images', 'cover_image', 'final_pdf'].includes(key)
      && !(depth > 0 && ['page_number', 'name', 'speaker'].includes(key))
    )
    return <div className={`human-fields depth-${Math.min(depth, 2)}`}>{entries.map(([key, child]) => <section className="human-field" key={key}><h4>{fieldLabel(key)}</h4><HumanContentValue value={child} fieldKey={key} depth={depth + 1} /></section>)}</div>
  }
  return <p>{String(value)}</p>
}

function HumanContent({ content, contentKey }: { content: unknown; contentKey?: string }) {
  let visible = content
  if (contentKey && isContentObject(content) && contentKey in content) visible = content[contentKey]
  return <div className="human-content"><HumanContentValue value={visible} fieldKey={contentKey} /></div>
}

function Messages({ project, onChanged }: { project: ProjectDetail; onChanged: () => Promise<void> }) {
  const [openId, setOpenId] = useState<number>()
  const [content, setContent] = useState<EventContent>()
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [editMode, setEditMode] = useState(false)
  const [jsonText, setJsonText] = useState('')
  const [feedback, setFeedback] = useState('')
  const [target, setTarget] = useState('artist')

  async function toggleEvent(event: EventItem) {
    if (openId === event.id) { setOpenId(undefined); setContent(undefined); return }
    setOpenId(event.id); setLoading(true); setError(''); setEditMode(false); setFeedback('')
    try {
      const result = await api.eventContent(project.id, event.id)
      setContent(result); setJsonText(JSON.stringify(result.content, null, 2))
      setTarget(result.approval?.assigned_agent || (event.agent === 'writer' || event.agent === 'designer' || event.agent === 'artist' || event.agent === 'reviewer' || event.agent === 'editor' ? event.agent : 'artist'))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể tải nội dung') } finally { setLoading(false) }
  }

  async function saveContent() {
    if (!openId) return
    setBusy(true); setError('')
    try {
      const parsed = JSON.parse(jsonText)
      await api.updateEventContent(project.id, openId, parsed)
      setContent(await api.eventContent(project.id, openId)); setEditMode(false); await onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'JSON chưa hợp lệ') } finally { setBusy(false) }
  }

  async function decide(decision: 'approve' | 'revise') {
    if (!content?.approval) return
    if (decision === 'revise' && feedback.trim().length < 3) { setError('Hãy ghi rõ nội dung cần agent sửa.'); return }
    setBusy(true); setError('')
    try { await api.decideApproval(project.id, content.approval.id, decision, feedback.trim(), target); await onChanged(); setOpenId(undefined); setContent(undefined) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể xử lý yêu cầu duyệt') } finally { setBusy(false) }
  }

  async function intervene() {
    if (!openId || feedback.trim().length < 3) { setError('Hãy ghi rõ yêu cầu can thiệp.'); return }
    setBusy(true); setError('')
    try { await api.intervene(project.id, openId, target, feedback.trim()); await onChanged(); setFeedback('') }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể giao lại công việc') } finally { setBusy(false) }
  }

  async function changeApproval(enabled: boolean, stages = project.approval_stages) {
    setBusy(true); setError('')
    try { await api.updateSettings(project.id, enabled, stages); await onChanged() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể lưu cấu hình duyệt') } finally { setBusy(false) }
  }

  function toggleStage(stage: ApprovalStage) {
    const stages = project.approval_stages.includes(stage) ? project.approval_stages.filter(item => item !== stage) : [...project.approval_stages, stage]
    changeApproval(project.approval_enabled, stages)
  }

  const events = project.events.slice().reverse()
  return <section className="workspace messages">
    <div className="workspace-title"><div><p className="eyebrow">AGENT COMMS</p><h2>Nhật ký giao tiếp</h2></div><span><UsersRound size={15} /> {events.length} sự kiện</span></div>
    <div className="approval-settings">
      <div><ShieldCheck size={18} /><div><strong>Duyệt nội dung theo yêu cầu</strong><span>Hệ thống tự dừng ở các bước bạn chọn và chờ quyết định ngay trong tin nhắn.</span></div></div>
      <label className="switch"><input type="checkbox" checked={project.approval_enabled} disabled={busy} onChange={event => changeApproval(event.target.checked)} /><i /></label>
      {project.approval_enabled && <div className="approval-stage-list">{(Object.keys(APPROVAL_LABELS) as ApprovalStage[]).map(stage => <label key={stage}><input type="checkbox" checked={project.approval_stages.includes(stage)} disabled={busy} onChange={() => toggleStage(stage)} />{APPROVAL_LABELS[stage]}</label>)}</div>}
    </div>
    <div className="activity-feed message-feed">{events.map(event => {
      const approvalId = Number(event.payload.approval_id || 0)
      const approval = project.approvals.find(item => item.id === approvalId)
      const opened = openId === event.id
      return <div className={`event-row message-event ${opened ? 'open' : ''}`} key={event.id}>
        <button className="message-summary" onClick={() => toggleEvent(event)}>
          <AgentAvatar id={event.agent} agents={project.agents} small /><div className="event-body"><div><strong>{agentLabel(event.agent, project.agents)}</strong><time>{formatTime(event.created_at)}</time></div><p>{event.message}</p><span className="event-kind">{event.event_type.replaceAll('_', ' ')}</span></div>
          {approval && <span className={`approval-tag ${approval.status}`}>{approval.status === 'pending' ? 'Chờ duyệt' : approval.status === 'approved' ? 'Đã duyệt' : 'Đã yêu cầu sửa'}</span>}<ChevronDown className="message-chevron" size={17} />
        </button>
        {opened && <div className="message-detail">
          {loading ? <div className="inline-loading"><RefreshCw className="spin" size={16} /> Đang tải nội dung…</div> : content && <>
            <div className="content-head"><strong>Nội dung bàn giao</strong>{content.content_key && <span>{fieldLabel(content.content_key)}</span>}</div>
            {editMode ? <textarea className="json-editor" value={jsonText} onChange={e => setJsonText(e.target.value)} /> : <HumanContent content={content.content} contentKey={content.content_key} />}
            {content.artifacts.length > 0 && <div className="message-artifacts">{content.artifacts.slice(0, 8).map(item => /\.(png|jpg|jpeg|webp)$/i.test(item.url) ? <a href={api.artifact(item.url)} target="_blank" rel="noreferrer" key={item.id}><img src={api.artifact(item.url)} alt={item.name} /><span>{item.name}</span></a> : <a className="file-link" href={api.artifact(item.url)} target="_blank" rel="noreferrer" key={item.id}><FileText size={18} />{item.name}</a>)}</div>}
            {project.status === 'running' || project.status === 'queued' || project.status === 'pause_requested' ? <div className="readonly-note"><LockKeyhole size={15} /><span><strong>Chỉ xem</strong> — Tạm dừng công việc để chỉnh sửa hoặc yêu cầu agent làm lại.</span></div> : null}
            {project.status === 'paused' && content.content_key && <div className="inline-actions">{editMode ? <><button className="secondary" onClick={() => setEditMode(false)}>Hủy</button><button className="primary" disabled={busy} onClick={saveContent}><Save size={15} /> Lưu nội dung</button></> : <button className="secondary" onClick={() => setEditMode(true)}><Settings2 size={15} /> Chỉnh sửa dữ liệu</button>}</div>}
            {content.approval?.status === 'pending' && project.status === 'awaiting_approval' && <div className="approval-actions"><h4>Duyệt ngay tại đây</h4><p>Nếu yêu cầu sửa ảnh, agent được giao sẽ tự thiết kế lại. Không có chức năng tải lên hoặc thay thế ảnh thủ công.</p><div className="revision-fields"><select value={target} onChange={e => setTarget(e.target.value)}><option value="writer">Biên kịch</option><option value="designer">Thiết kế nhân vật</option><option value="artist">Họa sĩ</option><option value="editor">Biên tập & dàn trang</option></select><textarea value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Mô tả cụ thể phần cần sửa…" /></div><div className="inline-actions"><button className="revision-button" disabled={busy} onClick={() => decide('revise')}>Yêu cầu sửa</button><button className="approve-button" disabled={busy} onClick={() => decide('approve')}><Check size={15} /> Duyệt nội dung</button></div></div>}
            {project.status === 'paused' && <div className="intervention-box"><h4>Can thiệp công việc</h4><p>Giao agent xử lý lại khi bạn tiếp tục dự án. Với hình ảnh, agent sẽ tự tạo lại từ yêu cầu này.</p><div className="revision-fields"><select value={target} onChange={e => setTarget(e.target.value)}><option value="writer">Biên kịch</option><option value="designer">Thiết kế nhân vật</option><option value="artist">Họa sĩ</option><option value="editor">Biên tập & dàn trang</option></select><textarea value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Yêu cầu can thiệp…" /></div><button className="revision-button" disabled={busy} onClick={intervene}>Giao agent làm lại</button></div>}
          </>}
          {error && <div className="form-error"><AlertTriangle size={15} />{error}</div>}
        </div>}
      </div>
    })}{events.length === 0 && <div className="empty-list">Chưa có tin nhắn.</div>}</div>
  </section>
}

function AgentManagement({ project, onChanged }: { project: ProjectDetail; onChanged: () => Promise<void> }) {
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState<WorkerRole>('writer')
  const [instructions, setInstructions] = useState('')
  const [color, setColor] = useState('#557a68')
  const [newModel, setNewModel] = useState('')
  const [newFallbacks, setNewFallbacks] = useState<string[]>([])
  const [newTemperature, setNewTemperature] = useState('')
  const [newImageModel, setNewImageModel] = useState('')
  const [busy, setBusy] = useState('')
  const [formError, setFormError] = useState('')
  const [modelAgentId, setModelAgentId] = useState('')
  const [primaryModel, setPrimaryModel] = useState('')
  const [fallbackModels, setFallbackModels] = useState<string[]>([])
  const [imageModel, setImageModel] = useState('')
  const [temperature, setTemperature] = useState('')
  const [modelOptions, setModelOptions] = useState(DEFAULT_TEXT_MODELS)
  const [imageOptions, setImageOptions] = useState<string[]>([])
  const [renameAgentId, setRenameAgentId] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const coreAgents = project.agents.filter(agent => agent.is_core)
  const customAgents = project.agents.filter(agent => !agent.is_core)
  const canAddAgent = project.status === 'paused'

  useEffect(() => {
    api.models().then(catalog => {
      setModelOptions(catalog.models.length ? catalog.models : DEFAULT_TEXT_MODELS)
      setImageOptions(catalog.image_model ? [catalog.image_model] : [])
    }).catch(() => { setModelOptions(DEFAULT_TEXT_MODELS) })
  }, [])

  function openModelEditor(agent: ProjectAgent) {
    setModelAgentId(agent.id); setPrimaryModel(agent.model || '')
    setFallbackModels(agent.fallback_models || []); setImageModel(agent.image_model || '')
    setTemperature(agent.temperature == null ? '' : String(agent.temperature)); setFormError('')
  }

  async function saveModels() {
    if (!modelAgentId) return
    setBusy('models'); setFormError('')
    try {
      await api.updateAgent(project.id, modelAgentId, {
        model: primaryModel.trim(),
        fallback_models: fallbackModels,
        image_model: imageModel.trim(), temperature: temperature.trim() ? Number(temperature) : null,
      })
      setModelAgentId(''); await onChanged()
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : 'Không thể lưu model') } finally { setBusy('') }
  }

  function toggleModel(list: string[], setList: (models: string[]) => void, model: string) {
    setList(list.includes(model) ? list.filter(item => item !== model) : [...list, model])
  }

  async function resetModels() {
    if (!modelAgentId) return
    setBusy('models'); setFormError('')
    try {
      await api.updateAgent(project.id, modelAgentId, {
        model: null, fallback_models: null, image_model: null, temperature: null,
      })
      setModelAgentId(''); await onChanged()
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : 'Không thể đặt lại model') } finally { setBusy('') }
  }

  async function createAgent() {
    if (name.trim().length < 2 || instructions.trim().length < 10) {
      setFormError('Hãy nhập tên và hướng dẫn ít nhất 10 ký tự.')
      return
    }
    setBusy('create'); setFormError('')
    try {
      await api.createAgent(project.id, {
        name: name.trim(), role_key: role, instructions: instructions.trim(), color,
        model: newModel || null, fallback_models: newFallbacks,
        image_model: ['designer', 'artist'].includes(role) ? newImageModel || null : null,
        temperature: newTemperature.trim() ? Number(newTemperature) : null,
      })
      setName(''); setRole('writer'); setInstructions(''); setColor('#557a68')
      setNewModel(''); setNewFallbacks([]); setNewTemperature(''); setNewImageModel(''); setShowForm(false)
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

  function openRename(agent: ProjectAgent) {
    if (agent.is_core) return
    setRenameAgentId(agent.id); setRenameValue(agent.name); setFormError('')
  }

  async function saveRename() {
    const nextName = renameValue.trim()
    if (!renameAgentId || nextName.length < 2) {
      setFormError('Tên agent phải có ít nhất 2 ký tự.')
      return
    }
    setBusy(renameAgentId); setFormError('')
    try {
      await api.updateAgent(project.id, renameAgentId, { name: nextName })
      setRenameAgentId(''); setRenameValue(''); await onChanged()
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : 'Không thể đổi tên agent') } finally { setBusy('') }
  }

  return <section className="workspace agents-workspace">
    <div className="workspace-title"><div><p className="eyebrow">PROJECT CREW</p><h2>Quản lý agent</h2></div><button className="primary add-agent-button" disabled={!canAddAgent} title={canAddAgent ? 'Thêm agent hỗ trợ' : 'Tạm dừng dự án trước khi thêm agent'} onClick={() => setShowForm(value => !value)}><UserPlus size={16} /> Thêm agent</button></div>
    <div className="agent-policy"><ShieldCheck size={19} /><div><strong>Workflow 6 vai trò được giữ nguyên</strong><span>Agent bổ sung là worker cùng vai trò; PM chia việc theo tên và có thể chạy song song.</span></div><b>{project.agents.length} agent</b></div>
    {!canAddAgent && <div className="agent-manage-lock"><LockKeyhole size={16} /><span><strong>Đang khóa thao tác thêm mới.</strong> Tạm dừng dự án nếu muốn thêm agent. Đổi model, đổi tên, bật/tắt và xóa agent hỗ trợ vẫn dùng được.</span></div>}
    {modelAgentId && <div className="model-form">
      <div className="agent-form-head"><div><p className="eyebrow">MODEL ROUTING</p><h3>Cấu hình model · {project.agents.find(agent => agent.id === modelAgentId)?.name}</h3></div><button className="icon-btn" onClick={() => setModelAgentId('')}><X size={18} /></button></div>
      <div className="model-form-grid"><label><span>Model chính</span><select value={primaryModel} onChange={event => { setPrimaryModel(event.target.value); setFallbackModels(items => items.filter(item => item !== event.target.value)) }}><option value="">Mặc định hệ thống ({modelOptions[0]})</option>{modelOptions.map(model => <option value={model} key={model}>{model}</option>)}</select></label><label><span>Độ sáng tạo</span><input type="number" min="0" max="2" step="0.05" value={temperature} onChange={event => setTemperature(event.target.value)} placeholder="Mặc định theo vai trò" /></label></div>
      <div className="model-choice-field"><span>Model dự phòng</span><div className="model-choice-list">{modelOptions.filter(model => model !== primaryModel).map(model => <label key={model} className={fallbackModels.includes(model) ? 'selected' : ''}><input type="checkbox" checked={fallbackModels.includes(model)} onChange={() => toggleModel(fallbackModels, setFallbackModels, model)} />{model}</label>)}</div></div>
      {['designer', 'artist'].includes(project.agents.find(agent => agent.id === modelAgentId)?.role_key || '') && <label className="model-image-field"><span>Model tạo ảnh</span><select value={imageModel} onChange={event => setImageModel(event.target.value)}><option value="">Mặc định hệ thống{imageOptions[0] ? ` (${imageOptions[0]})` : ''}</option>{imageOptions.map(model => <option value={model} key={model}>{model}</option>)}</select></label>}
      <p className="model-note">Thứ tự gọi: model chính → các model dự phòng. Hệ thống chỉ chuyển model khi hết quota hoặc token.</p>
      {formError && <div className="form-error"><AlertTriangle size={16} />{formError}</div>}
      <div className="agent-form-actions"><button className="secondary" disabled={busy === 'models'} onClick={resetModels}>Đặt mặc định</button><button className="primary" disabled={busy === 'models'} onClick={saveModels}>{busy === 'models' ? <RefreshCw className="spin" size={16} /> : <Save size={16} />} Lưu model</button></div>
    </div>}
    {showForm && canAddAgent && <div className="agent-form">
      <div className="agent-form-head"><div><p className="eyebrow">NEW ROLE WORKER</p><h3>Thêm agent hỗ trợ</h3></div><button className="icon-btn" onClick={() => setShowForm(false)}><X size={18} /></button></div>
      <div className="agent-form-grid"><label><span>Tên agent</span><input value={name} onChange={event => setName(event.target.value)} placeholder="Ví dụ: Mai" /></label><label><span>Vai trò hỗ trợ</span><select value={role} onChange={event => { setRole(event.target.value as WorkerRole); setNewImageModel('') }}>{WORKER_ROLES.map(item => <option value={item.key} key={item.key}>{item.label}</option>)}</select><small>{WORKER_ROLES.find(item => item.key === role)?.help}</small></label><label className="color-field"><span>Màu nhận diện</span><input type="color" value={color} onChange={event => setColor(event.target.value)} /></label></div>
      <label className="instruction-field"><span>Hướng dẫn và kỹ năng</span><textarea value={instructions} onChange={event => setInstructions(event.target.value)} placeholder="Mô tả phần việc agent này ưu tiên, phong cách và những điều phải kiểm tra…" /></label>
      <div className="new-agent-models"><div className="agent-form-grid"><label><span>Model chính</span><select value={newModel} onChange={event => { setNewModel(event.target.value); setNewFallbacks(items => items.filter(item => item !== event.target.value)) }}><option value="">Mặc định hệ thống ({modelOptions[0]})</option>{modelOptions.map(model => <option value={model} key={model}>{model}</option>)}</select></label><label><span>Độ sáng tạo</span><input type="number" min="0" max="2" step="0.05" value={newTemperature} onChange={event => setNewTemperature(event.target.value)} placeholder="Mặc định theo vai trò" /></label></div>{['designer', 'artist'].includes(role) && <label className="model-image-field"><span>Model tạo ảnh</span><select value={newImageModel} onChange={event => setNewImageModel(event.target.value)}><option value="">Mặc định hệ thống{imageOptions[0] ? ` (${imageOptions[0]})` : ''}</option>{imageOptions.map(model => <option value={model} key={model}>{model}</option>)}</select></label>}<div className="model-choice-field"><span>Model dự phòng</span><div className="model-choice-list">{modelOptions.filter(model => model !== newModel).map(model => <label key={model} className={newFallbacks.includes(model) ? 'selected' : ''}><input type="checkbox" checked={newFallbacks.includes(model)} onChange={() => toggleModel(newFallbacks, setNewFallbacks, model)} />{model}</label>)}</div></div></div>
      {formError && <div className="form-error"><AlertTriangle size={16} />{formError}</div>}
      <div className="agent-form-actions"><button className="secondary" onClick={() => setShowForm(false)}>Hủy</button><button className="primary" disabled={busy === 'create'} onClick={createAgent}>{busy === 'create' ? <RefreshCw className="spin" size={16} /> : <UserPlus size={16} />} Tạo agent</button></div>
    </div>}
    <div className="agent-group-head"><div><h3>Đội ngũ mặc định</h3><span>{coreAgents.length} agent lõi</span></div></div>
    <div className="management-agent-grid">{coreAgents.map(agent => <article className="management-agent-card core" key={agent.id} style={{ '--agent': agent.color } as React.CSSProperties}>
      <div className="management-agent-head"><AgentAvatar id={agent.key} /><div className="agent-card-actions"><button className="model-button" onClick={() => openModelEditor(agent)} title="Cấu hình model"><Settings2 size={14} /></button><span className="core-badge"><ShieldCheck size={12} /> Mặc định</span></div></div><h3>{agent.name}</h3><strong>{agent.role}</strong><p>{agent.instructions}</p><span className="model-summary">{agent.model || 'Model mặc định hệ thống'}</span>
    </article>)}</div>
    <div className="agent-group-head custom-head"><div><h3>Agent hỗ trợ theo vai trò</h3><span>{customAgents.length}/10 worker</span></div></div>
    {customAgents.length > 0 ? <div className="management-agent-grid">{customAgents.map(agent => <article className={`management-agent-card custom ${agent.enabled ? '' : 'disabled'}`} key={agent.id} style={{ '--agent': agent.color } as React.CSSProperties}>
      <div className="management-agent-head"><div className="custom-agent-avatar" style={{ background: agent.color }}>{agent.name.slice(0, 2).toUpperCase()}</div><div className="agent-card-actions"><button className="model-button" onClick={() => openModelEditor(agent)} title="Cấu hình model"><Settings2 size={14} /></button><button disabled={busy === agent.id} className="rename-agent-button" onClick={() => openRename(agent)} title="Đổi tên agent"><Pencil size={14} /></button><button disabled={busy === agent.id} className={`power-button ${agent.enabled ? 'enabled' : ''}`} onClick={() => toggleAgent(agent.id, !agent.enabled)} title={agent.enabled ? 'Tạm ngưng' : 'Kích hoạt'}><Power size={14} /></button><button disabled={busy === agent.id} className="remove-agent-button" onClick={() => removeAgent(agent.id, agent.name)} title="Xóa agent"><Trash2 size={14} /></button></div></div>
      {renameAgentId === agent.id ? <div className="agent-rename-form"><input autoFocus value={renameValue} maxLength={60} onChange={event => setRenameValue(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') saveRename(); if (event.key === 'Escape') setRenameAgentId('') }} /><button className="secondary" onClick={() => setRenameAgentId('')}>Hủy</button><button className="primary" disabled={busy === agent.id || renameValue.trim().length < 2} onClick={saveRename}><Save size={13} /> Lưu</button></div> : <h3>{agent.name}</h3>}<strong>{agent.role}</strong><p>{agent.instructions}</p><span className="model-summary">{agent.model || 'Model mặc định hệ thống'}</span><span className="agent-state"><i />{agent.enabled ? 'Sẵn sàng tham gia dự án' : 'Đang tạm ngưng'}</span>
    </article>)}</div> : <div className="empty-custom-agents"><Bot size={28} /><h3>Chưa có agent hỗ trợ</h3><p>Thêm worker cùng vai trò để PM chia việc và chạy song song.</p></div>}
  </section>
}

function artifactIcon(item: Artifact) { return item.kind.includes('image') || item.kind.includes('page') || item.kind.includes('cover') ? FileImage : item.kind === 'final_pdf' ? FileText : FileText }
function Artifacts({ artifacts, agents }: { artifacts: Artifact[]; agents: ProjectAgent[] }) {
  return <section className="workspace"><div className="workspace-title"><div><p className="eyebrow">OUTPUT LIBRARY</p><h2>Sản phẩm của xưởng</h2></div><span>{artifacts.length} tệp</span></div><div className="artifact-grid">{artifacts.map(item => {
    const Icon = artifactIcon(item); const isImage = /\.(png|jpg|jpeg|webp)$/i.test(item.url)
    return <article className="artifact-card" key={item.id}>{isImage ? <div className="artifact-preview" style={{ backgroundImage: `url(${api.artifact(item.url)})` }} /> : <div className="artifact-file"><Icon size={34} /></div>}<div className="artifact-info"><span>{item.kind.replaceAll('_', ' ')}</span><h4>{item.name}</h4><div><AgentAvatar id={item.agent} agents={agents} small /><a href={api.artifact(item.url)} target="_blank" rel="noreferrer"><Download size={15} /> Tải xuống</a></div></div></article>
  })}{artifacts.length === 0 && <div className="empty-artifacts"><GalleryVerticalEnd size={34} /><h3>Artifact sẽ xuất hiện ở đây</h3><p>Các agent đang chuẩn bị những file đầu tiên.</p></div>}</div></section>
}

function RouterModels() {
  const [catalog, setCatalog] = useState<RouterCatalog>()
  const [models, setModels] = useState<string[]>([])
  const [imageModel, setImageModel] = useState('')
  const [candidate, setCandidate] = useState('')
  const [busy, setBusy] = useState<'load' | 'save' | ''>('load')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy('load'); setError(''); setNotice('')
    try {
      const result = await api.routerModels()
      setCatalog(result); setModels(result.models); setImageModel(result.image_model)
      setCandidate(result.available_models.find(model => !result.models.includes(model) && model !== result.image_model) || '')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể đọc cấu hình 9Router') } finally { setBusy('') }
  }, [])

  useEffect(() => { load() }, [load])

  function move(index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= models.length) return
    setModels(items => { const next = [...items];[next[index], next[target]] = [next[target], next[index]]; return next })
  }

  function addModel() {
    if (!candidate || models.includes(candidate)) return
    setModels(items => [...items, candidate])
    setCandidate('')
  }

  async function save() {
    if (!models.length || !imageModel) return
    setBusy('save'); setError(''); setNotice('')
    try {
      const result = await api.updateRouterModels(models, imageModel)
      setCatalog(current => ({ ...result, available_models: current?.available_models || result.available_models }))
      setModels(result.models); setImageModel(result.image_model)
      setNotice('Đã lưu. Các lượt gọi agent tiếp theo sẽ dùng thứ tự model mới.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể lưu cấu hình') } finally { setBusy('') }
  }

  const available = catalog?.available_models || []
  const addable = available.filter(model => !models.includes(model) && model !== imageModel)
  const imageOptions = Array.from(new Set([...available, imageModel].filter(Boolean)))
  return <main className="router-page"><header className="router-page-head"><div><p className="eyebrow">GLOBAL MODEL ROUTING</p><h1>Quản lý model 9Router</h1><p>Thiết lập chuỗi model mặc định cho toàn bộ dự án. Model đầu tiên là model chính; các model sau chỉ được gọi khi hết quota hoặc token.</p></div><button className="secondary router-refresh" disabled={busy !== ''} onClick={load}><RefreshCw className={busy === 'load' ? 'spin' : ''} size={15} /> Đồng bộ 9Router</button></header>
    {error && <div className="router-alert error"><AlertTriangle size={16} />{error}</div>}
    {notice && <div className="router-alert success"><Check size={16} />{notice}</div>}
    <section className="router-status-card"><div><span>ENDPOINT</span><strong>{catalog?.router || 'Đang kết nối…'}</strong></div><div><span>API KEY</span><strong className={catalog?.api_key_configured ? 'connected' : 'disconnected'}>{catalog?.api_key_configured ? 'Đã cấu hình' : 'Chưa cấu hình'}</strong></div><div><span>CATALOG</span><strong>{available.length} model</strong></div></section>
    {catalog?.catalog_error && <div className="catalog-warning"><AlertTriangle size={14} /><span>Không thể đọc catalog trực tiếp: {catalog.catalog_error}. Bạn vẫn có thể chỉnh các model đã lưu.</span></div>}
    <div className="router-settings-grid"><section className="router-config-card"><div className="router-card-head"><div><span>TEXT ROUTING CHAIN</span><h2>Thứ tự gọi model</h2></div><b>{models.length}</b></div>
      <div className="router-model-list">{models.map((model, index) => <div className="router-model-row" key={model}><span className="model-order">{String(index + 1).padStart(2, '0')}</span><div><strong>{model}</strong><small>{index === 0 ? 'MODEL CHÍNH' : `FALLBACK ${index}`}</small></div><div className="model-row-actions"><button disabled={index === 0} onClick={() => move(index, -1)} title="Đưa lên">↑</button><button disabled={index === models.length - 1} onClick={() => move(index, 1)} title="Đưa xuống">↓</button><button className="remove" disabled={models.length === 1} onClick={() => setModels(items => items.filter(item => item !== model))} title="Xóa khỏi chuỗi"><X size={13} /></button></div></div>)}</div>
      <div className="add-router-model"><select value={candidate} onChange={event => setCandidate(event.target.value)}><option value="">Chọn model từ 9Router…</option>{addable.map(model => <option value={model} key={model}>{model}</option>)}</select><button className="secondary" disabled={!candidate} onClick={addModel}><Plus size={14} /> Thêm</button></div>
    </section><section className="router-config-card image-route-card"><div className="router-card-head"><div><span>IMAGE ROUTING</span><h2>Model tạo ảnh</h2></div><FileImage size={20} /></div><p>Model này được dùng để tạo ảnh tham chiếu, bìa và từng trang truyện.</p><label><span>Model ảnh mặc định</span><select value={imageModel} onChange={event => setImageModel(event.target.value)}>{imageOptions.map(model => <option value={model} key={model}>{model}</option>)}</select></label><div className="routing-note"><ShieldCheck size={17} /><span>Cấu hình được lưu ngoài dự án và áp dụng cho mọi dự án chưa đặt model riêng theo agent.</span></div></section></div>
    <footer className="router-save-bar"><div><strong>{models[0] || 'Chưa chọn model'}</strong><span> → {models.slice(1).join(' → ') || 'không có fallback'}</span></div><button className="primary" disabled={busy !== '' || !models.length || !imageModel} onClick={save}>{busy === 'save' ? <RefreshCw className="spin" size={15} /> : <Save size={15} />} Lưu cấu hình toàn hệ thống</button></footer>
  </main>
}

export default function App() {
  const initialRoute = readRoute()
  const [projects, setProjects] = useState<Project[]>([]); const [selected, setSelected] = useState<string | undefined>(initialRoute.projectId); const [detail, setDetail] = useState<ProjectDetail>(); const [tab, setTab] = useState<Tab>(initialRoute.tab); const [systemPage, setSystemPage] = useState<SystemPage>(initialRoute.page); const [modal, setModal] = useState(false); const [deleteModal, setDeleteModal] = useState(false); const [actionBusy, setActionBusy] = useState(false); const [error, setError] = useState('')
  const refreshList = useCallback(async () => { try { const data = await api.list(); setProjects(data); setSelected(current => current && data.some(project => project.id === current) ? current : undefined) } catch (e) { setError(e instanceof Error ? e.message : 'API unavailable') } }, [])
  const refreshDetail = useCallback(async () => { if (!selected) { setDetail(undefined); return } try { setDetail(await api.get(selected)); setError('') } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tải dự án') } }, [selected])
  useEffect(() => { refreshList() }, [refreshList]); useEffect(() => { refreshDetail() }, [refreshDetail])
  useEffect(() => { if (!selected) return; const timer = window.setInterval(() => { refreshDetail(); refreshList() }, ['running', 'queued', 'pause_requested'].includes(detail?.status || '') ? 2200 : 7000); return () => clearInterval(timer) }, [selected, detail?.status, refreshDetail, refreshList])
  useEffect(() => {
    const restoreRoute = () => {
      const route = readRoute()
      setSelected(current => { if (current !== route.projectId) setDetail(undefined); return route.projectId })
      setTab(route.tab); setSystemPage(route.page); setDeleteModal(false)
    }
    window.addEventListener('popstate', restoreRoute)
    return () => window.removeEventListener('popstate', restoreRoute)
  }, [])
  function navigate(path: string) { if (window.location.pathname !== path) window.history.pushState({}, '', path) }
  function created(project: Project) { navigate(`/projects/${project.id}/overview`); setProjects(p => [project, ...p]); setSelected(project.id); setSystemPage('home'); setModal(false); setTab('overview') }
  function openProject(id: string) { navigate(`/projects/${id}/overview`); setSelected(id); setSystemPage('home'); setDetail(undefined); setTab('overview') }
  function changeTab(nextTab: Tab) { if (!selected) return; navigate(`/projects/${selected}/${nextTab}`); setTab(nextTab) }
  function goHome() { navigate('/'); setSelected(undefined); setSystemPage('home'); setDetail(undefined); setDeleteModal(false); setTab('overview') }
  function openModels() { navigate('/models'); setSelected(undefined); setSystemPage('models'); setDetail(undefined); setDeleteModal(false); setTab('overview') }
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
  async function pauseProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try { await api.pause(detail.id); await refreshDetail(); await refreshList() } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tạm dừng dự án') } finally { setActionBusy(false) }
  }
  async function resumeProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try { await api.resume(detail.id); await refreshDetail(); await refreshList() } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tiếp tục dự án') } finally { setActionBusy(false) }
  }
  async function deleteProject() {
    if (!detail) return
    setActionBusy(true); setError('')
    try {
      await api.remove(detail.id)
      const remaining = projects.filter(project => project.id !== detail.id)
      navigate('/'); setProjects(remaining); setDetail(undefined); setSelected(undefined); setSystemPage('home'); setDeleteModal(false); setTab('overview')
    } catch (e) { setError(e instanceof Error ? e.message : 'Không thể xóa dự án') } finally { setActionBusy(false) }
  }
  return <div className="app-shell"><Sidebar projects={projects} selected={selected} systemPage={systemPage} onSelect={openProject} onCreate={() => setModal(true)} onHome={goHome} onModels={openModels} /><div className="app-main">
    {error && <div className="api-error"><AlertTriangle size={16} />{error}<button onClick={() => { refreshList(); refreshDetail() }}>Thử lại</button></div>}
    {systemPage === 'models' ? <RouterModels /> : !selected ? <HomePage projects={projects} onCreate={() => setModal(true)} onOpen={openProject} /> : detail ? <><Topbar project={detail} tab={tab} setTab={changeTab} busy={actionBusy} onRetry={retryProject} onPause={pauseProject} onResume={resumeProject} onStop={stopProject} onDelete={() => setDeleteModal(true)} onHome={goHome} /><div className="content">{detail.status === 'failed' && <div className="workflow-error"><AlertTriangle size={19} /><div><strong>Quy trình đã dừng ở {detail.progress}%</strong><span>{detail.error || 'Agent gặp lỗi không thể tự phục hồi.'}</span></div><button disabled={actionBusy} onClick={retryProject}><Play size={15} /> Tiếp tục từ bước này</button></div>}{detail.status === 'paused' && <div className="workflow-paused"><Pause size={19} /><div><strong>Dự án đã tạm dừng an toàn</strong><span>Bạn có thể mở tab Giao tiếp để chỉnh sửa hoặc giao agent làm lại, sau đó bấm Tiếp tục.</span></div></div>}{detail.status === 'awaiting_approval' && <div className="workflow-approval"><ShieldCheck size={19} /><div><strong>Đang chờ bạn duyệt nội dung</strong><span>Mở tin nhắn có nhãn “Chờ duyệt” trong tab Giao tiếp.</span></div><button onClick={() => changeTab('messages')}>Mở giao tiếp</button></div>}{tab === 'overview' && <Overview project={detail} />}{tab === 'list' && <TaskList project={detail} />}{tab === 'schedule' && <Schedule tasks={detail.tasks} agents={detail.agents} />}{tab === 'messages' && <Messages project={detail} onChanged={refreshDetail} />}{tab === 'agents' && <AgentManagement project={detail} onChanged={refreshDetail} />}{tab === 'artifacts' && <Artifacts artifacts={detail.artifacts} agents={detail.agents} />}</div></> : <div className="loader"><RefreshCw className="spin" /> Đang mở xưởng…</div>}
  </div>{modal && <NewProjectModal onClose={() => setModal(false)} onCreated={created} />}{deleteModal && detail && <ConfirmDeleteModal project={detail} busy={actionBusy} onClose={() => setDeleteModal(false)} onConfirm={deleteProject} />}</div>
}

