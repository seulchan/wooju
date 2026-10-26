import { createContext, useContext, type ReactNode } from 'react'

/**
 * Screen text follows the Mac's language (decided in docs/DECISIONS.md):
 * the server resolves it and returns it from /api/setup. Korean and English
 * are supported; anything else falls back to English.
 */
export type Lang = 'ko' | 'en'

const STRINGS = {
  welcomeTitle: { ko: 'Wooju에 오신 걸 환영해요', en: 'Welcome to Wooju' },
  welcomeBody: {
    ko: '자료를 넣으면 Wooju가 정리해서 믿을 수 있는 지식과 기억으로 남겨 줘요. 모든 내용은 이 Mac의 폴더에 저장돼요.',
    en: 'Drop things in and Wooju turns them into knowledge you can trust. Everything stays in a folder on this Mac.',
  },
  folderLabel: { ko: '저장할 폴더', en: 'Folder to keep everything in' },
  folderHint: {
    ko: '새 폴더면 Wooju가 만들어요. 이미 쓰던 Wooju 폴더를 골라도 돼요.',
    en: 'A new folder is created for you. You can also pick an existing Wooju folder.',
  },
  start: { ko: '시작하기', en: 'Start' },
  starting: { ko: '준비하는 중…', en: 'Getting ready…' },
  aiTitle: { ko: 'AI 연결', en: 'AI connection' },
  aiReady: { ko: '준비됐어요', en: 'Ready' },
  aiLocal: { ko: '이 Mac에서 실행되는 AI(Ollama)', en: 'AI running on this Mac (Ollama)' },
  openOllama: { ko: 'Ollama 설치 페이지 열기', en: 'Open the Ollama download page' },
  ollamaAfter: {
    ko: '설치를 마치면 자동으로 이어서 진행해요. 그동안에도 자료는 넣을 수 있어요.',
    en: 'Wooju continues by itself once it is installed. You can add files meanwhile.',
  },
  pullModel: { ko: '모델 받기', en: 'Download model' },
  useKey: { ko: '대신 API 키로 시작', en: 'Use an API key instead' },
  keyLabel: { ko: 'API 키', en: 'API key' },
  keySave: { ko: '연결하기', en: 'Connect' },
  keyNote: {
    ko: '키는 Mac 키체인에만 저장돼요. API 키를 쓰면 자료가 해당 회사로 전송돼요.',
    en: 'The key is stored only in the Mac keychain. With an API key, your material is sent to that company.',
  },
  dropTitle: { ko: '자료 넣기', en: 'Add material' },
  dropBody: { ko: 'PDF, 텍스트, HTML 파일을 여기에 끌어다 놓으세요.', en: 'Drag PDF, text, or HTML files here.' },
  choose: { ko: '파일 고르기', en: 'Choose files' },
  queued: { ko: '기다리는 중', en: 'Waiting' },
  working: { ko: '정리하는 중', en: 'Working' },
  waiting: { ko: 'AI 준비 기다리는 중', en: 'Waiting for AI' },
  done: { ko: '저장했어요', en: 'Saved' },
  failed: { ko: '실패', en: 'Failed' },
  review: { ko: '확인', en: 'Review' },
  history: { ko: '변경 기록', en: 'History' },
  reviewTitle: { ko: '확인할 것', en: 'To review' },
  reviewEmpty: { ko: '지금은 확인할 것이 없어요.', en: 'Nothing to review right now.' },
  approve: { ko: '반영', en: 'Apply' },
  reject: { ko: '버리기', en: 'Discard' },
  approveAll: { ko: '모두 반영', en: 'Apply all' },
  showDetail: { ko: '내용 보기', en: 'Show details' },
  hideDetail: { ko: '접기', en: 'Hide' },
  needsYou: { ko: '하나씩 확인 필요', en: 'Needs your check' },
  canBatch: { ko: '한 번에 반영 가능', en: 'Can apply together' },
  historyTitle: { ko: '변경 기록', en: 'History' },
  historyEmpty: { ko: '아직 변경 기록이 없어요.', en: 'No changes yet.' },
  undo: { ko: '되돌리기', en: 'Undo' },
  undone: { ko: '되돌림', en: 'Undone' },
  footer: {
    ko: '모든 변경은 기록되고 되돌릴 수 있어요',
    en: 'Every change is recorded and can be undone',
  },
} as const

export type StringKey = keyof typeof STRINGS

const LangContext = createContext<Lang>('en')

export function LangProvider({ lang, children }: { lang: string; children: ReactNode }) {
  return <LangContext.Provider value={lang === 'ko' ? 'ko' : 'en'}>{children}</LangContext.Provider>
}

export function useT(): (key: StringKey) => string {
  const lang = useContext(LangContext)
  return (key) => STRINGS[key][lang]
}

export function useLang(): Lang {
  return useContext(LangContext)
}
