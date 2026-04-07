const pptxgen = require("pptxgenjs");
const path = require("path");

const SCREENSHOTS = path.join(__dirname, "screenshots");
const OUTPUT = path.join(__dirname, "AI_Coding_Pipeline_Interface.pptx");

// Color palette — Midnight Executive with brand purple accent
const NAVY = "1E2044";
const WHITE = "FFFFFF";
const LIGHT_BG = "F5F6FA";
const ACCENT = "6366F1"; // brand indigo
const SUBTITLE_GRAY = "A0A3BD";
const BODY_DARK = "2D2F45";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10" x 5.625"
pres.author = "Dev-bot";
pres.title = "AI Coding Pipeline — Interface Overview";

// ═══════════════════════════════════════════════════════════
// TITLE SLIDE
// ═══════════════════════════════════════════════════════════
const titleSlide = pres.addSlide();
titleSlide.background = { color: NAVY };

// Logo
titleSlide.addImage({
  path: path.join(__dirname, "..", "frontend", "public", "logo-devbot.webp"),
  x: 4.25, y: 0.8, w: 1.5, h: 1.5,
});

// Title
titleSlide.addText("AI Coding Pipeline", {
  x: 0.5, y: 2.5, w: 9, h: 1,
  fontSize: 44, fontFace: "Trebuchet MS", bold: true,
  color: WHITE, align: "center", margin: 0,
});

// Subtitle line
titleSlide.addText([
  { text: "Интерфейс системы", options: { fontSize: 22, color: SUBTITLE_GRAY } },
], {
  x: 0.5, y: 3.4, w: 9, h: 0.6,
  fontFace: "Calibri", align: "center", margin: 0,
});

// Divider line
titleSlide.addShape(pres.shapes.LINE, {
  x: 3.5, y: 4.2, w: 3, h: 0,
  line: { color: ACCENT, width: 2 },
});

// Bottom info
titleSlide.addText("dev-bot.su  |  Версия 1.0", {
  x: 0.5, y: 4.5, w: 9, h: 0.5,
  fontSize: 14, fontFace: "Calibri",
  color: SUBTITLE_GRAY, align: "center", margin: 0,
});


// ═══════════════════════════════════════════════════════════
// SCREENSHOT SLIDES
// ═══════════════════════════════════════════════════════════
const slides = [
  { file: "01_login.png",                title: "Страница авторизации" },
  { file: "02_register.png",             title: "Регистрация нового пользователя" },
  { file: "03_kanban_board.png",         title: "Kanban-доска (основной экран)" },
  { file: "04_create_ticket.png",        title: "Создание новой карточки" },
  { file: "05_ticket_comments.png",      title: "Карточка — Комментарии" },
  { file: "06_ticket_attachments.png",   title: "Карточка — Вложения (drag & drop)" },
  { file: "07_dashboard.png",            title: "Dashboard — Метрики и аналитика" },
  { file: "08_settings_project.png",     title: "Настройки — Проект" },
  { file: "09_settings_ai_agents.png",   title: "Настройки — AI-агенты" },
  { file: "10_settings_integrations.png", title: "Настройки — Интеграции" },
  { file: "11_settings_notifications.png", title: "Настройки — Уведомления" },
  { file: "12_settings_profile.png",     title: "Настройки — Профиль пользователя" },
  { file: "13_about.png",               title: "О системе" },
  { file: "14_user_management.png",      title: "Управление пользователями" },
];

slides.forEach(({ file, title }, idx) => {
  const slide = pres.addSlide();
  slide.background = { color: LIGHT_BG };

  // Dark header bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.7,
    fill: { color: NAVY },
  });

  // Slide number in header
  slide.addText(`${idx + 1} / ${slides.length}`, {
    x: 8.5, y: 0, w: 1.3, h: 0.7,
    fontSize: 11, fontFace: "Calibri",
    color: SUBTITLE_GRAY, align: "right", valign: "middle", margin: 0,
  });

  // Title in header bar
  slide.addText(title, {
    x: 0.5, y: 0, w: 8, h: 0.7,
    fontSize: 18, fontFace: "Trebuchet MS", bold: true,
    color: WHITE, valign: "middle", margin: 0,
  });

  // Screenshot image — fill remaining space with padding
  // Slide is 10" x 5.625", header is 0.7", leave 0.15" padding
  const imgX = 0.3;
  const imgY = 0.85;
  const imgW = 9.4;
  const imgH = 4.55;

  // White card background with shadow for screenshot
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: imgX - 0.05, y: imgY - 0.05, w: imgW + 0.1, h: imgH + 0.1,
    fill: { color: WHITE }, rectRadius: 0.05,
    shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 135, opacity: 0.1 },
  });

  slide.addImage({
    path: path.join(SCREENSHOTS, file),
    x: imgX, y: imgY, w: imgW, h: imgH,
    rounding: false,
  });
});

// ═══════════════════════════════════════════════════════════
// SAVE
// ═══════════════════════════════════════════════════════════
pres.writeFile({ fileName: OUTPUT }).then(() => {
  console.log(`Presentation saved to: ${OUTPUT}`);
}).catch(err => {
  console.error("Error:", err);
  process.exit(1);
});
