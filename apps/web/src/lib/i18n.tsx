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
  chooseFolder: { ko: '폴더 고르기…', en: 'Choose folder…' },
  settings: { ko: '설정', en: 'Settings' },
  settingsTitle: { ko: '설정', en: 'Settings' },
  aiProvider: { ko: 'AI', en: 'AI' },
  providerOllama: { ko: '이 Mac (Ollama)', en: 'This Mac (Ollama)' },
  providerNote: {
    ko: 'Ollama는 자료가 Mac 밖으로 나가지 않아요. Claude와 OpenAI는 각자의 API 키로 쓰고, 자료가 해당 회사로 전송돼요.',
    en: 'With Ollama nothing leaves this Mac. Claude and OpenAI use your own API key and send your material to that company.',
  },
  installedModels: { ko: '설치된 모델', en: 'Installed models' },
  noModels: { ko: '아직 받은 모델이 없어요.', en: 'No models downloaded yet.' },
  ollamaOff: { ko: 'Ollama가 꺼져 있어요. Ollama 앱을 열면 모델 목록이 보여요.', en: 'Ollama is not running. Open the Ollama app to see your models.' },
  recommended: { ko: '추천', en: 'Recommended' },
  inUse: { ko: '사용 중', en: 'In use' },
  use: { ko: '이 모델 쓰기', en: 'Use this model' },
  moreModels: { ko: '다른 모델 받기', en: 'Download another model' },
  modelName: { ko: '모델 이름 (예: qwen3.5:9b)', en: 'Model name (e.g. qwen3.5:9b)' },
  download: { ko: '받기', en: 'Download' },
  downloading: { ko: '받는 중…', en: 'Downloading…' },
  browseModels: { ko: 'Ollama 모델 둘러보기', en: 'Browse Ollama models' },
  modelHint: {
    ko: 'Mac 메모리에 맞는 모델을 추천해요. 큰 모델은 더 정확하지만 느리고 메모리를 많이 써요.',
    en: 'The recommendation fits this Mac’s memory. Larger models are more accurate but slower and use more memory.',
  },
  cloudModel: { ko: '모델', en: 'Model' },
  getKey: { ko: '키 발급 페이지 열기', en: 'Open the key page' },
  saved: { ko: '저장했어요', en: 'Saved' },
  brainFolder: { ko: 'Brain 폴더', en: 'Brain folder' },
  changeFolder: { ko: '다른 폴더 열기…', en: 'Open another folder…' },
  language: { ko: '언어', en: 'Language' },
  languageNote: {
    ko: 'Mac 언어를 따라요. 바꾸려면 Mac의 시스템 설정 > 일반 > 언어 및 지역에서 바꾼 뒤 Wooju를 다시 열어 주세요.',
    en: 'Follows your Mac’s language. To change it, change System Settings > General > Language & Region, then reopen Wooju.',
  },
  ask: { ko: '질문하기', en: 'Ask' },
  askTitle: { ko: '내 자료에 질문하기', en: 'Ask your Brain' },
  askIntro: {
    ko: '저장한 자료와 노트만으로 답해요. 답마다 근거가 된 노트를 함께 보여 줘요.',
    en: 'Answers come only from your saved material and notes, with the notes each answer is based on.',
  },
  askPlaceholder: {
    ko: '예: 밸류업 지수에는 어떤 기업이 들어갔어?',
    en: 'e.g. Which companies are in the Value-up Index?',
  },
  askButton: { ko: '질문하기', en: 'Ask' },
  askThinking: {
    ko: '노트를 찾아 읽는 중… 이 Mac의 모델은 1분쯤 걸려요. 정리 중인 자료가 있으면 그 단계가 끝난 뒤에 답해요.',
    en: 'Finding and reading your notes… a model on this Mac takes about a minute, and waits for any file being organized to finish its step.',
  },
  askNothing: {
    ko: 'Brain에서 이 질문에 답할 자료를 찾지 못했어요. 관련 자료를 넣으면 답할 수 있어요.',
    en: 'Your Brain has nothing that answers this yet. Add material on it and ask again.',
  },
  askPartial: {
    ko: '노트에 없는 부분:',
    en: 'Not in your notes:',
  },
  askBasedOn: { ko: '근거', en: 'Based on' },
  askRelated: {
    ko: 'AI가 근거를 콕 집지 못했어요. 답할 때 읽은 노트예요:',
    en: 'The AI didn’t point to specific notes. These are the notes it read:',
  },
  askUnchecked: {
    ko: '근거가 표시되지 않은 답이에요. 아래 노트에서 직접 확인해 주세요.',
    en: 'This answer isn’t tied to specific notes. Check the notes below yourself.',
  },
  askCheck: {
    ko: 'AI가 노트를 요약한 답이에요. 중요한 판단 전에는 근거 노트를 직접 확인해 주세요.',
    en: 'This is the AI’s summary of your notes. Check the notes themselves before relying on it.',
  },
  askEarlier: { ko: '이전 질문', en: 'Earlier questions' },
  challengeTitle: { ko: '반론 검토', en: 'Challenge' },
  challengeIntro: {
    ko: 'AI가 이 가설을 Brain의 다른 자료와 대조해서, 무엇이 이걸 틀리게 만들 수 있는지 정리해요. 결과는 확인 화면에서 승인해야 노트에 들어가요. 상태는 바꾸지 않아요.',
    en: 'The AI tests this idea against the rest of your Brain and writes down what could make it wrong. It goes into the note only after you approve it in Review. The status is not changed.',
  },
  challengeButton: { ko: '반론 검토하기', en: 'Challenge this insight' },
  challengeWorking: { ko: '검토하는 중…', en: 'Reviewing…' },
  challengeReady: { ko: '검토 결과를 확인 화면에 올렸어요:', en: 'The review is waiting in Review:' },
  openReview: { ko: '확인하러 가기', en: 'Open Review' },
  phoneTitle: { ko: '휴대폰에서 보내기', en: 'Send from your phone' },
  phoneIntro: {
    ko: '밖에서 본 링크, 파일, 떠오른 생각을 보내 두면 Mac에서 Wooju가 열려 있을 때 저장해요.',
    en: 'Send links, files, and thoughts from anywhere; Wooju saves them when it’s open on your Mac.',
  },
  icloudTitle: { ko: 'iPhone: iCloud 폴더', en: 'iPhone: iCloud folder' },
  icloudSteps: {
    ko: 'iPhone에서 공유 → 파일에 저장 → iCloud Drive → Wooju Inbox를 고르세요. 파일은 자료로, 짧은 텍스트는 링크나 메모로 저장돼요.',
    en: 'On iPhone: Share → Save to Files → iCloud Drive → Wooju Inbox. Files become sources; short text becomes a link or memo.',
  },
  icloudOn: { ko: 'iCloud 폴더 쓰기', en: 'Use the iCloud folder' },
  icloudOff: { ko: '끄기', en: 'Turn off' },
  icloudMissing: {
    ko: '이 Mac에서 iCloud Drive가 꺼져 있어요. 시스템 설정 > Apple 계정 > iCloud에서 켤 수 있어요.',
    en: 'iCloud Drive is off on this Mac. Turn it on in System Settings > Apple Account > iCloud.',
  },
  telegramTitle: { ko: 'Telegram 봇', en: 'Telegram bot' },
  telegramStep1: { ko: 'Telegram에서 @BotFather를 열고 /newbot을 보내 봇을 만드세요.', en: 'In Telegram, open @BotFather and send /newbot to make a bot.' },
  telegramStep2: { ko: 'BotFather가 준 토큰을 아래에 붙여 넣으세요. 토큰은 Mac 키체인에만 저장돼요.', en: 'Paste the token BotFather gives you below. It’s kept only in the Mac keychain.' },
  telegramOpenFather: { ko: '@BotFather 열기', en: 'Open @BotFather' },
  telegramToken: { ko: '봇 토큰', en: 'Bot token' },
  telegramConnect: { ko: '봇 연결', en: 'Connect bot' },
  telegramPair: {
    ko: '마지막 단계: 아래 버튼으로 봇을 열고 시작(Start)을 누르세요. 그 대화만 Wooju에 보낼 수 있어요.',
    en: 'Last step: open your bot with the button below and press Start. Only that chat can send to Wooju.',
  },
  telegramOpen: { ko: 'Telegram 열기', en: 'Open Telegram' },
  telegramPaired: { ko: '연결됨', en: 'Connected' },
  telegramOff: { ko: '연결 끊기', en: 'Disconnect' },
  recentCaptures: { ko: '최근에 받은 것', en: 'Recently received' },
  smartTitle: { ko: '의미로 찾기', en: 'Search by meaning' },
  smartIntro: {
    ko: '단어가 달라도, 영어로 물어도 뜻이 같은 노트를 찾아요. 작은 모델(약 640MB)이 이 Mac에서만 돌아가요. Claude나 OpenAI를 써도 노트를 색인하려고 밖으로 보내지 않아요.',
    en: 'Finds notes that mean the same thing even in other words or the other language. A small model (about 640 MB) runs only on this Mac; your notes are never sent out to be indexed, even if you use Claude or OpenAI.',
  },
  smartOn: { ko: '켜짐', en: 'On' },
  smartIndexing: { ko: '노트 정리 중', en: 'Indexing notes' },
  smartGet: { ko: '모델 받고 켜기', en: 'Download and turn on' },
  smartNeedsOllama: {
    ko: 'Ollama가 켜져 있어야 해요. 지금은 단어로 찾아요.',
    en: 'Needs Ollama running. Search uses words for now.',
  },
  smartOff: { ko: '지금은 단어로 찾아요.', en: 'Search uses words for now.' },
  claudeTitle: { ko: 'Claude 연결', en: 'Claude connection' },
  claudeIntro: {
    ko: 'Claude 데스크톱 앱에서 이 Brain을 찾아 읽고 답할 수 있게 해요. Claude가 노트를 만들자고 하면 확인 화면에 올라오고, 승인해야 저장돼요.',
    en: 'Lets the Claude desktop app search and read this Brain. If Claude suggests a note, it waits in Review and is saved only when you approve it.',
  },
  claudePrivacy: {
    ko: 'Claude가 읽은 노트 내용은 Anthropic으로 전송돼요.',
    en: 'Notes Claude reads are sent to Anthropic.',
  },
  claudeConnect: { ko: 'Claude에 연결', en: 'Connect to Claude' },
  claudeDisconnect: { ko: '연결 해제', en: 'Disconnect' },
  claudeReconnect: { ko: '다시 연결', en: 'Reconnect' },
  claudeConnected: { ko: '연결됨', en: 'Connected' },
  claudeOutdated: {
    ko: '다른 위치의 Wooju에 연결돼 있어요. 앱을 옮겼다면 다시 연결해 주세요.',
    en: 'Claude points to Wooju in another location. If you moved the app, reconnect.',
  },
  claudeRestart: {
    ko: 'Claude 앱을 완전히 종료했다가 다시 열면 적용돼요. 그 다음 Claude에게 “내 Wooju에서 밸류업 관련 자료 찾아줘”처럼 물어보세요.',
    en: 'Quit Claude completely and open it again to finish. Then ask Claude something like “Search my Wooju for value-up notes.”',
  },
  claudeMissing: {
    ko: 'Claude 데스크톱 앱이 설치돼 있지 않아요.',
    en: 'The Claude desktop app isn’t installed.',
  },
  claudeDownload: { ko: 'Claude 받기', en: 'Get Claude' },
  claudeCode: { ko: 'Claude Code에서 쓰려면:', en: 'To use it in Claude Code:' },
  captureLabel: { ko: '링크나 메모', en: 'Link or memo' },
  alreadySaved: { ko: '이미 저장된 자료예요:', en: 'Already saved:' },
  retry: { ko: '다시 시도', en: 'Try again' },
  remove: { ko: '지우기', en: 'Remove' },
  capturePlaceholder: {
    ko: '링크를 붙여 넣거나 메모를 적어 주세요. 링크는 자료로 정리하고, 메모는 쓴 그대로 보관해요.',
    en: 'Paste a link or write a memo. Links become sources; memos are kept as you wrote them.',
  },
  captureSave: { ko: '저장', en: 'Save' },
  memoSaved: { ko: '메모를 저장했어요. 질문하기에서 찾을 수 있어요.', en: 'Memo saved. Ask can find it.' },
  linkSaved: { ko: '링크를 받았어요. 페이지를 정리하는 중이에요.', en: 'Link received. Organizing the page now.' },
  reviewDue: { ko: '검토할 때가 된 노트', en: 'Due for review' },
  reviewDueSince: { ko: '검토일', en: 'Review date' },
  reviewNext: { ko: '다음 검토', en: 'Next review' },
  review3m: { ko: '3개월 뒤', en: 'In 3 months' },
  review1y: { ko: '1년 뒤', en: 'In 1 year' },
  reviewClear: { ko: '날짜 지우기', en: 'Clear date' },
  reviewDone: { ko: '검토했어요 →', en: 'Reviewed →' },
  reviewNone: { ko: '검토 날짜가 없어요.', en: 'No review date.' },
  reviewHint: {
    ko: '실적, 가격, 계획처럼 금방 바뀌는 내용이면 다시 볼 날짜를 정해 두세요. 날짜가 지나면 홈에 보여요.',
    en: 'For things that go stale (earnings, prices, plans), set a date to look again. It shows on Home when it passes.',
  },
  reviewSet: { ko: '날짜 정하기', en: 'Set date' },
  footer: {
    ko: '모든 변경은 기록되고 되돌릴 수 있어요',
    en: 'Every change is recorded and can be undone',
  },
} as const

export type StringKey = keyof typeof STRINGS

const LangContext = createContext<Lang>('en')

/**
 * Screens written before i18n keep their English text in the source and wrap
 * it in `tr()`; KO maps that English to Korean. `pick()` is for sentences
 * that carry values. Both read the language set by the nearest LangProvider
 * (the language is fixed for the whole session).
 */
let current: Lang = 'en'

export function tr(text: string): string {
  return current === 'ko' ? (KO[text] ?? text) : text
}

/** Reset between tests; the app sets the language through LangProvider. */
export function setCurrentLang(lang: Lang): void {
  current = lang
}

export function pick(en: string, ko: string): string {
  return current === 'ko' ? ko : en
}

export function LangProvider({ lang, children }: { lang: string; children: ReactNode }) {
  const value: Lang = lang === 'ko' ? 'ko' : 'en'
  current = value
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

const KO: Record<string, string> = {
  // navigation and shell
  Home: '홈',
  Knowledge: '알게 된 것',
  Insights: '발견한 연결',
  Insight: '발견한 연결',
  Sources: '자료',
  Source: '자료',
  Memory: '나에 대해',
  Projects: '프로젝트',
  Areas: '영역',
  Settings: '설정',
  Search: '찾기',
  'Search the Brain…': 'Brain에서 찾기…',
  'Search the Brain': 'Brain에서 찾기',
  Offline: '연결 끊김',
  'Brain ready': '준비됨',
  'Not configured': '설정 필요',
  'Checking backend': '확인 중',
  "Can't reach Wooju's server. Reopen the app if this continues.":
    'Wooju 서버에 연결할 수 없어요. 계속되면 앱을 다시 열어 주세요.',
  // home
  'Loading Brain summary…': 'Brain을 불러오는 중…',
  'Your Brain is empty': '아직 Brain이 비어 있어요',
  'Drop a file above to add your first note.': '위에 파일을 넣으면 첫 노트가 만들어져요.',
  'What do I know?': '무엇을 알고 있나',
  'Main areas': '주요 영역',
  'What is connected?': '무엇이 연결되어 있나',
  'What needs attention?': '무엇을 확인해야 하나',
  'Loading map…': '지도를 불러오는 중…',
  'Mapping connections…': '연결을 그리는 중…',
  'What changed?': '무엇이 바뀌었나',
  Period: '기간',
  'No changes in this period.': '이 기간에는 바뀐 것이 없어요.',
  "This is your first visit — showing the Brain's current changes. Your next visit will compare against this session.":
    '처음 방문이라 지금까지의 변경을 보여 줘요. 다음부터는 이번 방문 이후의 변경을 보여 줘요.',
  'Since last visit': '지난 방문 이후',
  '7 days': '7일',
  '30 days': '30일',
  'All time': '전체',
  'No connections yet': '아직 연결이 없어요',
  'Relationships between knowledge and insights will appear here.':
    '지식과 발견한 연결 사이의 관계가 여기에 나타나요.',
  'Open record →': '노트 열기 →',
  // attention
  'Finding items to review…': '확인할 것을 찾는 중…',
  'Nothing needs attention right now': '지금은 확인할 것이 없어요',
  'No provisional or candidate insights, open questions, contested claims, or unresolved references were found in the Brain.':
    '검토 중인 연결, 열린 질문, 엇갈리는 주장, 깨진 참조가 없어요.',
  'Provisional insight': '잠정 연결',
  'Provisional insights': '잠정 연결',
  'Original title': '원제',
  'Due for review': '검토할 때가 된 노트',
  'Due: review': '검토할 때',
  "Notes that break the Brain's rules": '규칙에 맞지 않는 노트',
  "Note that breaks the Brain's rules": '규칙에 맞지 않는 노트',
  'Rule problem': '규칙 문제',
  'Candidate insight': '후보 연결',
  'Candidate insights': '후보 연결',
  'Open question': '열린 질문',
  'Open questions': '열린 질문',
  'Contested claim': '엇갈리는 주장',
  'Contested claims': '엇갈리는 주장',
  'Unresolved derivation': '찾을 수 없는 근거',
  'Unresolved derivations': '찾을 수 없는 근거',
  'Unresolved link': '깨진 링크',
  'Unresolved links': '깨진 링크',
  'Unresolved reference': '찾을 수 없는 참조',
  Provisional: '잠정',
  Candidate: '후보',
  Established: '확립',
  Contested: '엇갈림',
  Rejected: '기각',
  Superseded: '대체됨',
  // lists
  'Loading knowledge…': '불러오는 중…',
  'Durable wiki notes — concepts, overviews, models, and how-tos.':
    '오래 두고 쓸 지식이에요. 개념, 개요, 사고방식, 방법을 모아 둬요.',
  All: '전체',
  'No knowledge notes': '아직 정리된 지식이 없어요',
  'No notes for this filter': '이 조건에 맞는 노트가 없어요',
  'Loading insights…': '불러오는 중…',
  Status: '상태',
  Kind: '종류',
  Type: '유형',
  Category: '분류',
  'No insights': '아직 발견한 연결이 없어요',
  'No insights for these filters': '이 조건에 맞는 연결이 없어요',
  'Loading sources…': '불러오는 중…',
  'No sources': '아직 자료가 없어요',
  'Search titles, aliases, and note text…': '제목과 본문에서 찾기…',
  'Full-text search across every indexed note.': '모든 노트의 본문에서 찾아요.',
  'Searching…': '찾는 중…',
  'No results': '결과가 없어요',
  'Memory / Projects / Areas': '나에 대해 / 프로젝트 / 영역',
  // record detail
  'Supporting evidence': '근거',
  Challenge: '반론 검토',
  Boundaries: '범위와 한계',
  'Loading record…': '불러오는 중…',
  'Record not found': '노트를 찾을 수 없어요',
  'This note has no body content.': '본문이 없는 노트예요.',
  Details: '정보',
  Path: '위치',
  Modified: '수정',
  Aliases: '다른 이름',
  Tags: '태그',
  'Original artifact': '원본',
  Author: '저자',
  Date: '날짜',
  File: '파일',
  Derivation: '근거가 된 노트',
  Links: '링크',
  // shared states
  'Loading…': '불러오는 중…',
  'Something went wrong': '문제가 생겼어요',
  'Something went wrong.': '문제가 생겼어요.',
  'Try again': '다시 시도',
  'Page not found': '페이지를 찾을 수 없어요',
  // note types (titleCase output)
  Article: '기사',
  Docs: '문서',
  Paper: '논문',
  Book: '책',
  Spec: '명세',
  Repo: '저장소',
  Video: '영상',
  Podcast: '팟캐스트',
  Course: '강의',
  Conversation: '대화',
  Experience: '경험',
  Other: '기타',
  Concept: '개념',
  Concepts: '개념',
  Overview: '개요',
  Overviews: '개요',
  Question: '질문',
  Questions: '질문',
  'How To': '방법',
  'How Tos': '방법',
  'Mental Model': '사고방식',
  'Mental Models': '사고방식',
  Pattern: '패턴',
  Connection: '연결',
  Tension: '긴장',
  Implication: '시사점',
  Hypothesis: '가설',
  Project: '프로젝트',
  Area: '영역',
}

export function useT(): (key: StringKey) => string {
  const lang = useContext(LangContext)
  return (key) => STRINGS[key][lang]
}

export function useLang(): Lang {
  return useContext(LangContext)
}
