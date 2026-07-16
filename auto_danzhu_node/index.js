#!/usr/bin/env node
/**
 * Auto Login & Nhap Ma Moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)
 *
 * Flow:
 *   1. Garena Connect OAuth: prelogin -> login -> token/grant -> token/exchange
 *   2. ITOP Game Login: get aov_token, GameOpenId, gameToken
 *   3. AOV Cloud: danzhu/usecode - nhap ma moi ban be
 *
 * Usage:
 *   node index.js --accounts accounts.txt --code MA_MOI --datadome "COOKIE"
 *
 * Lay DataDome cookie:
 *   1. Mo link Garena OAuth trong trinh duyet
 *   2. F12 -> Application -> Cookies -> garena.com -> datadome
 *   3. Copy gia tri cookie
 *
 * accounts.txt format (moi dong 1 tai khoan):
 *   username:password
 *   email:password
 */

const crypto = require("crypto");
const fs = require("fs");
const https = require("https");
const http = require("http");
const { URL, URLSearchParams } = require("url");
const querystring = require("querystring");

// ── Constants ───────────────────────────────────────────────────────────
const GARENA_APP_ID = "100054";
const GARENA_CLIENT_SECRET =
  "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515";
const GARENA_REDIRECT_URI = "gop100054://auth/";
const GARENA_CONNECT_BASE = "https://100054.connect.garena.com";

const ITOP_BASE = "https://itop.kg.garena.vn";
const ITOP_GAMEID = "1137";
const ITOP_CHANNELID = "10";

const AOV_CLOUD_BASE = "https://aovcloud.garena.com";
const AOV_PARTITION = "1011";
const AOV_AREA_ID = "1";

const BROWSER_UA =
  "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.46 " +
  "Mobile Safari/537.36";
const UNITY_UA =
  "UnityPlayer/2022.3.5f1 (UnityWebRequest/1.0, libcurl/8.1.1-DEV)";
const SDK_UA = "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)";
const DEVICE_ID = "57-28-68-BF-29-40-4E-F0-32-40-8B-66-3A-12-E1-F7";

// ── Helpers ─────────────────────────────────────────────────────────────
function md5(str) {
  return crypto.createHash("md5").update(str, "utf8").digest("hex");
}

function garenaPasswordHash(password, v2) {
  return md5(md5(password) + v2);
}

function tsMs() {
  return String(Date.now());
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Minimal HTTP client that tracks cookies across requests (same-session).
 */
class HttpClient {
  constructor(initialCookies = {}) {
    this.cookies = { ...initialCookies };
  }

  _parseCookies(headers) {
    const raw = headers["set-cookie"];
    if (!raw) return;
    const arr = Array.isArray(raw) ? raw : [raw];
    for (const line of arr) {
      const m = line.match(/^([^=]+)=([^;]*)/);
      if (m) this.cookies[m[1]] = m[2];
    }
  }

  _cookieHeader() {
    return Object.entries(this.cookies)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  }

  request(urlStr, options = {}) {
    return new Promise((resolve, reject) => {
      const url = new URL(urlStr);
      const isHttps = url.protocol === "https:";
      const mod = isHttps ? https : http;

      const headers = { ...(options.headers || {}) };
      const ck = this._cookieHeader();
      if (ck) headers["Cookie"] = ck;

      const reqOpts = {
        method: options.method || "GET",
        hostname: url.hostname,
        port: url.port || (isHttps ? 443 : 80),
        path: url.pathname + url.search,
        headers,
        timeout: 15000,
      };

      const req = mod.request(reqOpts, (res) => {
        this._parseCookies(res.headers);
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          resolve({ status: res.statusCode, headers: res.headers, body });
        });
      });
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("Request timeout"));
      });
      if (options.body) req.write(options.body);
      req.end();
    });
  }

  async get(url, headers = {}) {
    return this.request(url, { method: "GET", headers });
  }

  async post(url, body, headers = {}) {
    return this.request(url, { method: "POST", body, headers });
  }
}

// ── Garena Connect Login ────────────────────────────────────────────────
async function garenaLogin(account, password, dataDomeCookie = "") {
  const initialCookies = {};
  if (dataDomeCookie) {
    initialCookies["datadome"] = dataDomeCookie;
  }
  const client = new HttpClient(initialCookies);
  const referer =
    `${GARENA_CONNECT_BASE}/universal/oauth?` +
    `redirect_uri=${encodeURIComponent(GARENA_REDIRECT_URI)}` +
    `&response_type=code&client_id=${GARENA_APP_ID}` +
    `&login_scenario=normal&locale=vi-VN`;

  const commonHeaders = {
    "User-Agent": BROWSER_UA,
    Accept: "application/json, text/plain, */*",
    "X-Requested-With": "com.garena.game.kgvn",
    Referer: referer,
  };

  // Step 0: Load OAuth page for cookies
  const oauthUrl =
    `${GARENA_CONNECT_BASE}/api/universal/oauth?` +
    `redirect_uri=${encodeURIComponent(GARENA_REDIRECT_URI)}` +
    `&response_type=code&client_id=${GARENA_APP_ID}` +
    `&login_scenario=normal&locale=vi-VN&format=json&id=${tsMs()}`;
  await client.get(oauthUrl, commonHeaders);

  // Step 1: Prelogin
  const preloginUrl =
    `${GARENA_CONNECT_BASE}/api/prelogin?` +
    `app_id=${GARENA_APP_ID}` +
    `&account=${encodeURIComponent(account)}` +
    `&format=json&id=${tsMs()}`;
  const preRes = await client.get(preloginUrl, commonHeaders);

  if (preRes.status === 403) {
    let data;
    try {
      data = JSON.parse(preRes.body);
    } catch {
      data = {};
    }
    if (data.url && data.url.includes("captcha-delivery")) {
      throw new Error(
        `DataDome captcha! Cookie het han hoac khong hop le.\n` +
        `  -> Lay cookie moi tu trinh duyet (xem huong dan trong file)`
      );
    }
    throw new Error(`Prelogin 403 - DataDome chan. Dung --datadome COOKIE`);
  }
  const preData = JSON.parse(preRes.body);
  const { v1, v2 } = preData;
  if (!v2) throw new Error(`Prelogin khong tra ve v2: ${preRes.body}`);

  // Step 2: Login
  const pwHash = garenaPasswordHash(password, v2);
  const loginUrl =
    `${GARENA_CONNECT_BASE}/api/login?` +
    `app_id=${GARENA_APP_ID}` +
    `&account=${encodeURIComponent(account)}` +
    `&password=${pwHash}` +
    `&redirect_uri=${encodeURIComponent(GARENA_REDIRECT_URI)}` +
    `&format=json&id=${tsMs()}`;
  const loginRes = await client.get(loginUrl, commonHeaders);

  if (loginRes.status === 403) {
    throw new Error("Login bi captcha (DataDome).");
  }
  const loginData = JSON.parse(loginRes.body);
  if (loginData.error) {
    throw new Error(`Login loi: ${JSON.stringify(loginData)}`);
  }
  const sessionKey = loginData.session_key;
  if (!sessionKey) {
    throw new Error(`Khong co session_key: ${loginRes.body}`);
  }
  console.log(`  [+] Garena login OK: uid=${loginData.uid}`);

  // Step 3: Token Grant
  const grantBody = querystring.stringify({
    client_id: GARENA_APP_ID,
    response_type: "code",
    redirect_uri: GARENA_REDIRECT_URI,
    login_scenario: "normal",
    format: "json",
    id: tsMs(),
  });
  const grantRes = await client.post(
    `${GARENA_CONNECT_BASE}/oauth/token/grant`,
    grantBody,
    {
      ...commonHeaders,
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      Origin: GARENA_CONNECT_BASE,
    }
  );
  const grantData = JSON.parse(grantRes.body);
  const code = grantData.code;
  if (!code) throw new Error(`Token grant khong co code: ${grantRes.body}`);

  // Step 4: Token Exchange
  const exchangeBody = querystring.stringify({
    code,
    grant_type: "authorization_code",
    login_scenario: "normal",
    redirect_uri: GARENA_REDIRECT_URI,
    source: "2",
    client_secret: GARENA_CLIENT_SECRET,
    client_id: GARENA_APP_ID,
  });
  const exchClient = new HttpClient();
  const exchRes = await exchClient.post(
    `${GARENA_CONNECT_BASE}/oauth/token/exchange`,
    exchangeBody,
    {
      "User-Agent": SDK_UA,
      "Content-Type": "application/x-www-form-urlencoded",
    }
  );
  const exchData = JSON.parse(exchRes.body);
  if (!exchData.access_token) {
    throw new Error(`Token exchange loi: ${exchRes.body}`);
  }
  console.log(
    `  [+] Token exchange OK: open_id=${exchData.open_id.substring(0, 16)}...`
  );

  return {
    accessToken: exchData.access_token,
    openId: exchData.open_id,
    uid: exchData.uid,
    sessionKey,
  };
}

// ── ITOP Game Login ─────────────────────────────────────────────────────
async function itopLogin(accessToken, openId) {
  const ts = String(Math.floor(Date.now() / 1000));
  const seqId = `${ITOP_GAMEID}-auto-${ts}`;

  const body = JSON.stringify({
    openid: openId,
    token: accessToken,
    channelid: parseInt(ITOP_CHANNELID),
    gameid: parseInt(ITOP_GAMEID),
    os: 1,
    lang: "",
    seq: seqId,
    ts,
  });

  const params = new URLSearchParams({
    channelid: ITOP_CHANNELID,
    encrypt: "0",
    gameid: ITOP_GAMEID,
    lang: "",
    os: "1",
    seq: seqId,
    ts,
    version: "null",
  });

  const client = new HttpClient();
  const res = await client.post(
    `${ITOP_BASE}/v2/auth/login?${params.toString()}`,
    body,
    {
      "Content-Type": "application/json",
      Host: "itop.kg.garena.vn",
    }
  );

  let result;
  try {
    result = JSON.parse(res.body);
  } catch {
    throw new Error(
      `ITOP login response khong phai JSON (co the can encrypt=1): ${res.body.substring(0, 200)}`
    );
  }

  if (result.ret !== 0) {
    throw new Error(`ITOP login loi: ${JSON.stringify(result)}`);
  }

  const tokenInfo = result.token_info || {};
  return {
    aovToken: tokenInfo.aov_token || result.aov_token || "",
    gameOpenId: result.openid || tokenInfo.openid || "",
    gameToken: tokenInfo.game_token || result.game_token || "",
    raw: result,
  };
}

// ── danzhu/usecode ──────────────────────────────────────────────────────
async function useInvitationCode(aovToken, gameOpenId, gameToken, invCode) {
  const userinfo = JSON.stringify({
    uin: gameOpenId,
    areaID: AOV_AREA_ID,
    roleID: gameOpenId,
    platform: "1",
    accType: "Guest",
    partitionID: AOV_PARTITION,
  });

  const body = JSON.stringify({ invitationCode: invCode });

  const client = new HttpClient();
  const res = await client.post(
    `${AOV_CLOUD_BASE}/vn_online/danzhu/usecode`,
    body,
    {
      Host: "aovcloud.garena.com",
      "User-Agent": UNITY_UA,
      Accept: "*/*",
      "Content-Type": "application/json; charset=utf-8",
      aov_token: aovToken,
      GameOpenId: gameOpenId,
      gameToken: gameToken,
      channel: "1",
      platId: "1",
      partition: AOV_PARTITION,
      areaId: AOV_AREA_ID,
      userinfo,
      lang: "VN",
      version: "0.0.6",
      gmTimeStamp: String(Math.floor(Date.now() / 1000)),
      "X-Unity-Version": "2022.3.5f1",
    }
  );

  return JSON.parse(res.body);
}

// ── Process one account ─────────────────────────────────────────────────
async function processAccount(account, password, invCode, delay, dataDomeCookie = "") {
  console.log(`\n${"=".repeat(60)}`);
  console.log(`[*] Dang xu ly: ${account}`);
  console.log(`${"=".repeat(60)}`);

  // Step 1: Garena login
  let garenaResult;
  try {
    garenaResult = await garenaLogin(account, password, dataDomeCookie);
  } catch (e) {
    console.log(`  [!] Garena login THAT BAI: ${e.message}`);
    return false;
  }

  await sleep(delay);

  // Step 2: ITOP login
  let itopResult;
  try {
    itopResult = await itopLogin(garenaResult.accessToken, garenaResult.openId);
    console.log(`  [+] ITOP login OK: GameOpenId=${itopResult.gameOpenId}`);
  } catch (e) {
    console.log(`  [!] ITOP login THAT BAI: ${e.message}`);
    console.log(
      `  [!] Neu loi 'encrypt', can dung INTL SDK encryption (xem README).`
    );
    return false;
  }

  await sleep(delay);

  // Step 3: Use invitation code
  try {
    const result = await useInvitationCode(
      itopResult.aovToken,
      itopResult.gameOpenId,
      itopResult.gameToken,
      invCode
    );

    const code = result.code ?? -1;
    const msg = result.msg || "";
    const reward = result.rewardDanzhuNum || 0;

    if (code === 0) {
      console.log(`  [+] NHAP MA THANH CONG! Reward: ${reward} dan chu`);
      const ownCode = result.inviteData?.invitationCode || "";
      if (ownCode) {
        console.log(`  [+] Ma moi cua tai khoan nay: ${ownCode}`);
      }
    } else {
      console.log(`  [!] Nhap ma that bai: code=${code}, msg=${msg}`);
      if (code === 1) {
        console.log(`      -> Co the da nhap ma roi hoac ma khong hop le`);
      }
    }
    return code === 0;
  } catch (e) {
    console.log(`  [!] Nhap ma loi: ${e.message}`);
    return false;
  }
}

// ── Load accounts ───────────────────────────────────────────────────────
function loadAccounts(filepath) {
  const lines = fs.readFileSync(filepath, "utf8").split("\n");
  const accounts = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf(":");
    if (idx === -1) {
      console.log(`  [!] Sai format (can account:password): ${line}`);
      continue;
    }
    const account = line.substring(0, idx).trim();
    const password = line.substring(idx + 1).trim();
    if (account && password) accounts.push({ account, password });
  }
  return accounts;
}

// ── CLI ─────────────────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);

  let accountsFile = "";
  let invCode = "";
  let delay = 3000;
  let accountDelay = 5000;
  let dataDomeCookie = "";
  let getCookie = false;

  for (let i = 0; i < args.length; i++) {
    if ((args[i] === "--accounts" || args[i] === "-a") && args[i + 1]) {
      accountsFile = args[++i];
    } else if ((args[i] === "--code" || args[i] === "-c") && args[i + 1]) {
      invCode = args[++i];
    } else if ((args[i] === "--delay" || args[i] === "-d") && args[i + 1]) {
      delay = parseFloat(args[++i]) * 1000;
    } else if (args[i] === "--account-delay" && args[i + 1]) {
      accountDelay = parseFloat(args[++i]) * 1000;
    } else if (args[i] === "--datadome" && args[i + 1]) {
      dataDomeCookie = args[++i];
    } else if (args[i] === "--get-cookie") {
      getCookie = true;
    }
  }

  if (getCookie) {
    console.log(`\nHUONG DAN LAY DATADOME COOKIE:`);
    console.log(`\n1. Mo link sau trong trinh duyet:`);
    console.log(`   https://100054.connect.garena.com/universal/oauth?redirect_uri=gop100054%3A%2F%2Fauth%2F&response_type=code&client_id=100054&login_scenario=normal&locale=vi-VN`);
    console.log(`\n2. Doi trang login hien ra (3-5 giay)`);
    console.log(`\n3. Lay cookie datadome:`);
    console.log(`   Chrome: F12 -> Application -> Cookies -> garena.com -> datadome`);
    console.log(`   Tren Android: dung Kiwi Browser (co DevTools) hoac app Cookie Editor`);
    console.log(`\n4. Chay tool voi cookie:`);
    console.log(`   node index.js -a accounts.txt -c MA_MOI --datadome "GIA_TRI_COOKIE"\n`);
    process.exit(0);
  }

  if (!accountsFile || !invCode) {
    console.log(
      "Usage: node index.js --accounts accounts.txt --code MA_MOI --datadome COOKIE"
    );
    console.log("");
    console.log("Options:");
    console.log("  --accounts, -a   File danh sach tai khoan (account:password)");
    console.log("  --code, -c       Ma moi ban be can nhap");
    console.log("  --datadome       DataDome cookie (lay tu trinh duyet)");
    console.log("  --delay, -d      Delay giua cac buoc (giay, mac dinh: 3)");
    console.log(
      "  --account-delay  Delay giua cac tai khoan (giay, mac dinh: 5)"
    );
    console.log("  --get-cookie     Huong dan lay DataDome cookie");
    process.exit(1);
  }

  if (!dataDomeCookie) {
    console.log("[!] CANH BAO: Khong co --datadome cookie, se bi DataDome chan!");
    console.log("[!] Lay cookie: node index.js --get-cookie\n");
  }

  const accounts = loadAccounts(accountsFile);
  if (accounts.length === 0) {
    console.log("[!] Khong tim thay tai khoan nao trong file.");
    process.exit(1);
  }

  console.log(`[*] Da doc ${accounts.length} tai khoan`);
  console.log(`[*] Ma moi: ${invCode}`);
  if (dataDomeCookie) {
    console.log(`[*] DataDome cookie: ${dataDomeCookie.substring(0, 40)}...`);
  }
  console.log(`[*] Delay giua cac buoc: ${delay / 1000}s`);
  console.log(`[*] Delay giua cac tai khoan: ${accountDelay / 1000}s`);

  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < accounts.length; i++) {
    if (i > 0) {
      console.log(
        `\n[*] Cho ${accountDelay / 1000}s truoc tai khoan tiep theo...`
      );
      await sleep(accountDelay);
    }

    const { account, password } = accounts[i];
    const ok = await processAccount(account, password, invCode, delay, dataDomeCookie);
    if (ok) successCount++;
    else failCount++;
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log(
    `[*] HOAN TAT: ${successCount} thanh cong, ${failCount} that bai / ${accounts.length} tong`
  );
  console.log(`${"=".repeat(60)}`);
}

main().catch((e) => {
  console.error(`[!] Loi khong xu ly duoc: ${e.message}`);
  process.exit(1);
});
