import { chromium } from '../e2e/node_modules/playwright/index.mjs';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const BASE = 'http://localhost:55128';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // 1. Login page
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01_login.png') });
  console.log('1. Login page');

  // 2. Register page
  await page.goto(`${BASE}/register`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02_register.png') });
  console.log('2. Register page');

  // 3. Login and go to board
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input[type="email"]', 'demo@devbot.su');
  await page.fill('input[type="password"]', 'demo1234');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/board');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03_kanban_board.png') });
  console.log('3. Kanban board');

  // 4. New Ticket modal
  const newTicketBtn = page.locator('button', { hasText: 'New Ticket' });
  await newTicketBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04_create_ticket.png') });
  console.log('4. Create ticket modal');

  // Close modal
  const cancelBtn = page.locator('button', { hasText: 'Cancel' });
  await cancelBtn.click();
  await page.waitForTimeout(300);

  // 5. Ticket detail - Comments
  // Get first ticket via API
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  const ticketsRes = await page.evaluate(async (t) => {
    const r = await fetch('/api/v1/projects/600840ec-6f10-4d1c-a6cd-e01c4e56e594/tickets?per_page=1', {
      headers: { 'Authorization': `Bearer ${t}` }
    });
    return r.json();
  }, token);

  const ticketId = ticketsRes.items?.[0]?.id;
  if (ticketId) {
    await page.goto(`${BASE}/tickets/${ticketId}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05_ticket_comments.png') });
    console.log('5. Ticket detail - Comments');

    // 6. Attachments tab
    const attachTab = page.locator('button', { hasText: 'Attachments' });
    await attachTab.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06_ticket_attachments.png') });
    console.log('6. Ticket detail - Attachments');
  }

  // 7. Dashboard
  await page.goto(`${BASE}/dashboard`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07_dashboard.png') });
  console.log('7. Dashboard');

  // 8. Settings - Project
  await page.goto(`${BASE}/settings`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08_settings_project.png') });
  console.log('8. Settings - Project');

  // 9. Settings - AI Agents
  const aiTab = page.locator('button', { hasText: 'AI Agents' });
  await aiTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '09_settings_ai_agents.png') });
  console.log('9. Settings - AI Agents');

  // 10. Settings - Integrations
  const intTab = page.locator('button', { hasText: 'Integrations' });
  await intTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '10_settings_integrations.png') });
  console.log('10. Settings - Integrations');

  // 11. Settings - Notifications
  const notifTab = page.locator('button', { hasText: 'Notifications' });
  await notifTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '11_settings_notifications.png') });
  console.log('11. Settings - Notifications');

  // 12. Settings - Profile
  const profTab = page.locator('button', { hasText: 'Profile' });
  await profTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '12_settings_profile.png') });
  console.log('12. Settings - Profile');

  // 13. About
  await page.goto(`${BASE}/about`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '13_about.png') });
  console.log('13. About page');

  // 14. User Management
  await page.goto(`${BASE}/admin/users`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '14_user_management.png') });
  console.log('14. User Management');

  await browser.close();
  console.log('\nAll screenshots saved to docs/screenshots/');
}

main().catch(e => { console.error(e); process.exit(1); });
