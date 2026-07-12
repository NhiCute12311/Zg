#!/usr/bin/env node
/**
 * Garena Browser Login — dùng puppeteer để bypass DataDome.
 * Mở headless browser, navigate tới login page, điền TK/MK,
 * bắt API response để lấy token.
 *
 * Usage: node garena_browser_login.js <account> <password>
 * Output: JSON trên stdout
 */

const APP_ID = "100054";
const REDIRECT_URI = "gop100054://auth/";
const CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515";

const LOGIN_PAGE = `https://${APP_ID}.connect.garena.com/universal/oauth?` +
    `redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
    `&response_type=code&client_id=${APP_ID}&login_scenario=normal&locale=vi-VN`;

async function findChromium() {
    const { execSync } = require("child_process");
    const paths = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chromium-browser",
        "/opt/pw-browsers/chromium/chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ];
    for (const p of paths) {
        try {
            require("fs").accessSync(p);
            return p;
        } catch (_) {}
    }
    // Try which
    try {
        const w = execSync("which chromium-browser 2>/dev/null || which chromium 2>/dev/null || which google-chrome 2>/dev/null", { encoding: "utf-8" }).trim();
        if (w) return w;
    } catch (_) {}

    // Try playwright chromium
    try {
        const glob = require("path");
        const pwPath = "/opt/pw-browsers";
        const fs = require("fs");
        if (fs.existsSync(pwPath)) {
            const dirs = fs.readdirSync(pwPath);
            for (const d of dirs) {
                const chrome = glob.join(pwPath, d, "chrome");
                if (fs.existsSync(chrome)) return chrome;
                const chrome2 = glob.join(pwPath, d, "chrome-linux", "chrome");
                if (fs.existsSync(chrome2)) return chrome2;
            }
        }
    } catch (_) {}

    return null;
}

async function main() {
    const args = process.argv.slice(2);
    if (args.length < 2) {
        console.error("Usage: node garena_browser_login.js <account> <password>");
        process.exit(1);
    }
    const account = args[0];
    const password = args[1];

    let puppeteer;
    try {
        puppeteer = require("puppeteer-core");
    } catch (_) {
        try {
            puppeteer = require("puppeteer");
        } catch (_2) {
            console.error(JSON.stringify({
                error: "puppeteer not installed",
                fix: "npm install puppeteer-core"
            }));
            process.exit(1);
        }
    }

    const chromePath = await findChromium();
    if (!chromePath) {
        console.error(JSON.stringify({
            error: "chromium not found",
            fix: "pkg install chromium (Termux) hoac apt install chromium-browser"
        }));
        process.exit(1);
    }

    const captured = {
        prelogin: null,
        login: null,
        grant: null,
        exchange: null,
    };

    let browser;
    try {
        browser = await puppeteer.launch({
            executablePath: chromePath,
            headless: "new",
            args: [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
                "--disable-extensions",
            ],
        });

        const page = await browser.newPage();

        await page.setUserAgent(
            "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) " +
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/149.0.7827.159 " +
            "Mobile Safari/537.36"
        );

        // Intercept API responses
        page.on("response", async (resp) => {
            const url = resp.url();
            try {
                if (url.includes("/api/prelogin") && resp.status() === 200) {
                    const body = await resp.json();
                    if (body.v1) captured.prelogin = body;
                }
                if (url.includes("/api/login") && resp.status() === 200) {
                    const body = await resp.json();
                    if (body.session_key) captured.login = body;
                }
                if (url.includes("/oauth/token/grant") && resp.status() === 200) {
                    const body = await resp.json();
                    if (body.code) captured.grant = body;
                }
                if (url.includes("/oauth/token/exchange") && resp.status() === 200) {
                    const body = await resp.json();
                    if (body.access_token) captured.exchange = body;
                }
            } catch (_) {}
        });

        // Navigate to login page
        await page.goto(LOGIN_PAGE, { waitUntil: "networkidle2", timeout: 30000 });

        // Wait for DataDome to finish + login form to appear
        await page.waitForSelector('input[name="account"], input[name="username"], input[type="text"]', { timeout: 20000 });
        await sleep(1000);

        // Try to find and fill the account field
        const accountField = await page.$('input[name="account"]')
            || await page.$('input[name="username"]')
            || await page.$('input[type="text"]');

        if (!accountField) {
            throw new Error("Cannot find account input field");
        }

        // Clear and type account
        await accountField.click({ clickCount: 3 });
        await accountField.type(account, { delay: 50 });

        // Find and fill password
        const pwField = await page.$('input[name="password"]')
            || await page.$('input[type="password"]');

        if (!pwField) {
            throw new Error("Cannot find password input field");
        }

        await pwField.click({ clickCount: 3 });
        await pwField.type(password, { delay: 50 });

        // Find and click login button
        await sleep(500);
        const loginBtn = await page.$('button[type="submit"]')
            || await page.$('button.btn-login')
            || await page.$('button.login-btn')
            || await page.$('button');

        if (loginBtn) {
            await loginBtn.click();
        } else {
            await page.keyboard.press("Enter");
        }

        // Wait for login API responses
        const deadline = Date.now() + 25000;
        while (Date.now() < deadline) {
            if (captured.exchange) break;
            if (captured.login && captured.login.error) break;
            await sleep(500);
        }

        // Check for login error
        if (captured.login && captured.login.error) {
            console.log(JSON.stringify({
                error: "login_failed",
                detail: captured.login.error
            }));
            process.exit(1);
        }

        if (!captured.exchange) {
            // Try getting grant + exchange manually if we have session_key
            if (captured.login && captured.login.session_key) {
                // Session established, try to get OAuth tokens via page
                const cookies = await page.cookies();
                const ddCookie = cookies.find(c => c.name === "datadome");
                console.log(JSON.stringify({
                    partial: true,
                    session_key: captured.login.session_key,
                    uid: captured.login.uid,
                    username: captured.login.username,
                    grant: captured.grant,
                    datadome_cookie: ddCookie ? ddCookie.value : null,
                    all_cookies: cookies.map(c => c.name + "=" + c.value).join("; "),
                }));
                process.exit(0);
            }

            console.log(JSON.stringify({
                error: "timeout",
                detail: "Login did not complete in time",
                captured_keys: Object.keys(captured).filter(k => captured[k])
            }));
            process.exit(1);
        }

        // Success — output full result
        const result = {
            uid: captured.exchange.uid || (captured.grant && captured.grant.uid),
            garena_uid: captured.login ? captured.login.uid : null,
            open_id: captured.exchange.open_id || (captured.grant && captured.grant.open_id),
            access_token: captured.exchange.access_token,
            refresh_token: captured.exchange.refresh_token || "",
            session_key: captured.login ? captured.login.session_key : "",
            expiry_time: captured.exchange.expiry_time || 0,
            expires_in: captured.exchange.expires_in || 0,
            platform: captured.exchange.platform || 3,
        };

        console.log(JSON.stringify(result));
        process.exit(0);

    } catch (e) {
        console.log(JSON.stringify({
            error: "browser_error",
            detail: e.message
        }));
        process.exit(1);
    } finally {
        if (browser) {
            try { await browser.close(); } catch (_) {}
        }
    }
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

main();
