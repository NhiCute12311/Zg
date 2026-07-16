package com.autodanzhu;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.*;
import android.widget.*;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONObject;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class MainActivity extends AppCompatActivity {

    // ── Garena / Game constants ──
    static final String APP_ID = "100054";
    static final String CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515";
    static final String REDIRECT_URI = "gop100054://auth/";
    static final String CONNECT_BASE = "https://100054.connect.garena.com";
    static final String ITOP_BASE = "https://itop.kg.garena.vn";
    static final String AOV_CLOUD = "https://aovcloud.garena.com";
    static final String GAMEID = "1137";
    static final String CHANNELID = "10";
    static final String PARTITION = "1011";
    static final String AREA_ID = "1";
    static final String UNITY_UA = "UnityPlayer/2022.3.5f1 (UnityWebRequest/1.0, libcurl/8.1.1-DEV)";

    static final String LOGIN_URL = CONNECT_BASE + "/universal/oauth?"
            + "redirect_uri=" + Uri.encode(REDIRECT_URI)
            + "&response_type=code&client_id=" + APP_ID
            + "&login_scenario=normal&locale=vi-VN";

    // ── Views ──
    EditText etFilePath, etCode;
    Button btnStart, btnStop, btnPickFile, btnToggleWeb;
    TextView tvStatus, tvLog;
    ScrollView scrollLog;
    WebView webView;
    Spinner spEvent;

    // ── State ──
    final Handler mainHandler = new Handler(Looper.getMainLooper());
    final ExecutorService executor = Executors.newSingleThreadExecutor();
    List<String[]> accounts = new ArrayList<>();
    int currentIndex = 0;
    String inviteCode = "";
    volatile boolean running = false;
    boolean webVisible = false;
    String usecodeEventPath = "danzhu";

    // token/grant or token/exchange capture
    volatile String capturedCode = null;
    volatile String capturedAccessToken = null;
    volatile String capturedOpenId = null;
    volatile boolean tokenProcessing = false;

    ActivityResultLauncher<Intent> filePickerLauncher;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etFilePath = findViewById(R.id.etFilePath);
        etCode = findViewById(R.id.etCode);
        btnStart = findViewById(R.id.btnStart);
        btnStop = findViewById(R.id.btnStop);
        btnPickFile = findViewById(R.id.btnPickFile);
        btnToggleWeb = findViewById(R.id.btnToggleWeb);
        tvStatus = findViewById(R.id.tvStatus);
        tvLog = findViewById(R.id.tvLog);
        scrollLog = findViewById(R.id.scrollLog);
        webView = findViewById(R.id.webView);
        spEvent = findViewById(R.id.spEvent);

        setupWebView();

        filePickerLauncher = registerForActivityResult(
                new ActivityResultContracts.StartActivityForResult(),
                result -> {
                    if (result.getResultCode() == Activity.RESULT_OK && result.getData() != null) {
                        Uri uri = result.getData().getData();
                        if (uri != null) {
                            etFilePath.setText(uri.toString());
                        }
                    }
                });

        btnPickFile.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("text/plain");
            filePickerLauncher.launch(intent);
        });

        btnStart.setOnClickListener(v -> startProcessing());
        btnStop.setOnClickListener(v -> stopProcessing());
        btnToggleWeb.setOnClickListener(v -> toggleWebView());
    }

    @SuppressLint("SetJavaScriptEnabled")
    void setupWebView() {
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        ws.setUserAgentString(
                "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) "
                + "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.39 "
                + "Mobile Safari/537.36");
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        ws.setDatabaseEnabled(true);
        ws.setAllowFileAccess(true);

        webView.addJavascriptInterface(new WebBridge(), "AutoDanzhu");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("gop100054://")) {
                    log("[WebView] Redirect caught: " + url.substring(0, Math.min(url.length(), 80)));
                    parseRedirectUrl(url);
                    return true;
                }
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (url.contains("connect.garena.com") && running) {
                    log("[WebView] Page loaded, injecting hooks...");
                    injectHooks();
                    mainHandler.postDelayed(() -> autoFillAndSubmit(), 2000);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    log("[WebView] Error: " + error.getDescription());
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage cm) {
                if (cm.message().startsWith("[AD]")) {
                    log("[JS] " + cm.message());
                }
                return true;
            }
        });
    }

    // ── JavaScript injection ──

    void injectHooks() {
        String js = "(function() {"
            + "if(window.__adHooked) return; window.__adHooked=true;"
            + "console.log('[AD] Hooks installed');"
            // Hook XMLHttpRequest to capture API responses
            + "var origOpen = XMLHttpRequest.prototype.open;"
            + "var origSend = XMLHttpRequest.prototype.send;"
            + "XMLHttpRequest.prototype.open = function(m, u) {"
            + "  this._adUrl = u; this._adMethod = m;"
            + "  return origOpen.apply(this, arguments);"
            + "};"
            + "XMLHttpRequest.prototype.send = function() {"
            + "  var self = this;"
            + "  this.addEventListener('load', function() {"
            + "    try {"
            + "      var u = self._adUrl || '';"
            + "      if(u.indexOf('/oauth/token/grant') !== -1 || u.indexOf('/oauth/token/exchange') !== -1) {"
            + "        console.log('[AD] Captured: ' + u);"
            + "        AutoDanzhu.onTokenResponse(u, self.responseText, self.status);"
            + "      } else if(u.indexOf('/api/login') !== -1) {"
            + "        console.log('[AD] Login response: ' + self.status);"
            + "        AutoDanzhu.onLoginResponse(self.responseText, self.status);"
            + "      } else if(u.indexOf('/api/prelogin') !== -1) {"
            + "        console.log('[AD] Prelogin: ' + self.status);"
            + "      }"
            + "    } catch(e) { console.log('[AD] Hook err: ' + e); }"
            + "  });"
            + "  return origSend.apply(this, arguments);"
            + "};"
            // Also hook fetch API
            + "var origFetch = window.fetch;"
            + "window.fetch = function(input, init) {"
            + "  return origFetch.apply(this, arguments).then(function(resp) {"
            + "    var u = typeof input === 'string' ? input : (input.url || '');"
            + "    if(u.indexOf('/oauth/token') !== -1) {"
            + "      resp.clone().text().then(function(body) {"
            + "        console.log('[AD] fetch captured: ' + u);"
            + "        AutoDanzhu.onTokenResponse(u, body, resp.status);"
            + "      });"
            + "    }"
            + "    return resp;"
            + "  });"
            + "};"
            + "})();";
        webView.evaluateJavascript(js, null);
    }

    void autoFillAndSubmit() {
        if (!running || currentIndex >= accounts.size()) return;

        String[] acc = accounts.get(currentIndex);
        String username = acc[0].replace("\\", "\\\\").replace("'", "\\'");
        String password = acc[1].replace("\\", "\\\\").replace("'", "\\'");

        String js = "(function() {"
            + "var retries = 0;"
            + "function setVal(el, val) {"
            + "  var s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            + "  s.call(el, val);"
            + "  el.dispatchEvent(new Event('input', {bubbles:true}));"
            + "  el.dispatchEvent(new Event('change', {bubbles:true}));"
            + "}"
            + "function tryFill() {"
            + "  var pwdInput = document.querySelector('input[type=\"password\"]');"
            + "  if(!pwdInput) {"
            + "    retries++;"
            + "    if(retries < 15) {"
            + "      console.log('[AD] Password field not found, retry ' + retries + '...');"
            + "      setTimeout(tryFill, 800);"
            + "    } else {"
            + "      console.log('[AD] Give up finding password field after 15 retries');"
            + "    }"
            + "    return;"
            + "  }"
            + "  var inputs = document.querySelectorAll('input');"
            + "  var userInput = null;"
            + "  for(var i = 0; i < inputs.length; i++) {"
            + "    if(inputs[i].type !== 'password' && inputs[i].type !== 'hidden'"
            + "       && inputs[i].type !== 'checkbox' && inputs[i].type !== 'submit') {"
            + "      userInput = inputs[i]; break;"
            + "    }"
            + "  }"
            + "  if(!userInput) { console.log('[AD] Username field not found'); return; }"
            + "  console.log('[AD] Auto-filling: " + username + "');"
            + "  setVal(userInput, '" + username + "');"
            + "  setVal(pwdInput, '" + password + "');"
            + "  setTimeout(function() {"
            + "    var btns = document.querySelectorAll('button');"
            + "    for(var i=0; i<btns.length; i++) {"
            + "      var b = btns[i];"
            + "      var t = (b.textContent || '').toLowerCase();"
            + "      if(t.indexOf('log') !== -1 || t.indexOf('sign') !== -1"
            + "         || t.indexOf('ng nh') !== -1 || t.indexOf('dang nhap') !== -1) {"
            + "        console.log('[AD] Clicking: ' + b.textContent.trim());"
            + "        b.click(); return;"
            + "      }"
            + "    }"
            + "    var primary = document.querySelector('button.primary, button[type=\"submit\"]');"
            + "    if(primary) { console.log('[AD] Clicking primary'); primary.click(); return; }"
            + "    if(btns.length > 0) { console.log('[AD] Clicking first btn'); btns[0].click(); }"
            + "  }, 500);"
            + "}"
            + "tryFill();"
            + "})();";
        webView.evaluateJavascript(js, null);
    }

    // ── JavaScript Interface ──

    class WebBridge {
        @JavascriptInterface
        public void onTokenResponse(String url, String body, int status) {
            log("[Token] " + url.substring(url.lastIndexOf('/') + 1) + " status=" + status);
            try {
                JSONObject json = new JSONObject(body);
                if (url.contains("token/exchange")) {
                    capturedAccessToken = json.optString("access_token", "");
                    capturedOpenId = json.optString("open_id", "");
                    if (!capturedAccessToken.isEmpty()) {
                        log("[Token] access_token + open_id captured!");
                        mainHandler.post(() -> onTokensCaptured());
                    }
                } else if (url.contains("token/grant")) {
                    String code = json.optString("code", "");
                    if (!code.isEmpty()) {
                        capturedCode = code;
                        log("[Token] auth code captured, waiting for exchange...");
                    }
                    String redirectUri = json.optString("redirect_uri", "");
                    if (!redirectUri.isEmpty() && redirectUri.contains("code=")) {
                        log("[Token] redirect_uri has code");
                    }
                }
            } catch (Exception e) {
                log("[Token] Parse error: " + e.getMessage());
            }
        }

        @JavascriptInterface
        public void onLoginResponse(String body, int status) {
            try {
                JSONObject json = new JSONObject(body);
                if (json.has("error")) {
                    log("[Login] Error: " + json.optString("error"));
                } else {
                    String username = json.optString("username", "");
                    int uid = json.optInt("uid", 0);
                    log("[Login] OK: " + username + " (uid=" + uid + ")");
                }
            } catch (Exception e) {
                log("[Login] Parse error: " + e.getMessage());
            }
        }
    }

    void parseRedirectUrl(String url) {
        try {
            Uri uri = Uri.parse(url);
            String code = uri.getQueryParameter("code");
            if (code != null && !code.isEmpty()) {
                capturedCode = code;
                log("[Redirect] Got auth code, doing token exchange...");
                executor.submit(this::doTokenExchange);
            }
            String token = uri.getQueryParameter("access_token");
            if (token != null && !token.isEmpty()) {
                capturedAccessToken = token;
                capturedOpenId = uri.getQueryParameter("open_id");
                mainHandler.post(this::onTokensCaptured);
            }
        } catch (Exception e) {
            log("[Redirect] Parse error: " + e.getMessage());
        }
    }

    // ── Account Processing ──

    void startProcessing() {
        String filePath = etFilePath.getText().toString().trim();
        inviteCode = etCode.getText().toString().trim();

        if (filePath.isEmpty()) {
            toast("Chon file accounts"); return;
        }
        if (inviteCode.isEmpty()) {
            toast("Nhap ma moi"); return;
        }

        accounts.clear();
        try {
            BufferedReader reader;
            if (filePath.startsWith("content://")) {
                InputStream is = getContentResolver().openInputStream(Uri.parse(filePath));
                reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
            } else {
                reader = new BufferedReader(new FileReader(filePath));
            }
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                String[] parts = line.split(":", 2);
                if (parts.length == 2 && !parts[0].isEmpty() && !parts[1].isEmpty()) {
                    accounts.add(parts);
                }
            }
            reader.close();
        } catch (Exception e) {
            log("Loi doc file: " + e.getMessage());
            toast("Khong doc duoc file");
            return;
        }

        if (accounts.isEmpty()) {
            toast("File khong co account nao (format: account:password)");
            return;
        }

        usecodeEventPath = spEvent.getSelectedItem().toString();

        log("=== BAT DAU ===");
        log("Accounts: " + accounts.size() + " | Code: " + inviteCode + " | Event: " + usecodeEventPath);

        running = true;
        currentIndex = 0;
        btnStart.setEnabled(false);
        btnStop.setEnabled(true);

        processNextAccount();
    }

    void stopProcessing() {
        running = false;
        log("=== DA DUNG ===");
        btnStart.setEnabled(true);
        btnStop.setEnabled(false);
        tvStatus.setText("Da dung");
    }

    void processNextAccount() {
        if (!running || currentIndex >= accounts.size()) {
            log("\n=== XONG TAT CA " + accounts.size() + " ACCOUNTS ===");
            stopProcessing();
            return;
        }

        String[] acc = accounts.get(currentIndex);
        String label = (currentIndex + 1) + "/" + accounts.size();
        log("\n[" + label + "] Dang nhap: " + acc[0]);
        tvStatus.setText("Dang xu ly: " + acc[0] + " (" + label + ")");

        capturedCode = null;
        capturedAccessToken = null;
        capturedOpenId = null;
        tokenProcessing = false;

        CookieManager.getInstance().removeAllCookies(success -> {
            CookieManager.getInstance().flush();
            webView.clearCache(true);
            webView.clearHistory();
            mainHandler.postDelayed(() -> {
                log("[WebView] Loading login page...");
                webView.loadUrl(LOGIN_URL);
            }, 500);
        });

        // Timeout: if nothing happens in 60s, skip this account
        mainHandler.postDelayed(() -> {
            if (running && capturedAccessToken == null && capturedCode == null) {
                log("[!] Timeout 60s - co the can captcha. Hien WebView de check.");
                if (!webVisible) toggleWebView();
            }
        }, 60000);
    }

    void onTokensCaptured() {
        if (!running) return;
        if (capturedAccessToken == null || capturedAccessToken.isEmpty()) return;
        if (tokenProcessing) return;
        tokenProcessing = true;

        log("[+] Got tokens! Calling ITOP + usecode...");
        executor.submit(() -> {
            try {
                doItopAndUsecode(capturedAccessToken, capturedOpenId);
            } catch (Exception e) {
                log("[!] Error: " + e.getMessage());
            }
            mainHandler.post(() -> {
                currentIndex++;
                if (running) {
                    mainHandler.postDelayed(this::processNextAccount, 2000);
                }
            });
        });
    }

    void doTokenExchange() {
        if (capturedCode == null || capturedCode.isEmpty()) return;
        try {
            log("[Exchange] POST token/exchange...");
            String body = "code=" + capturedCode
                    + "&grant_type=authorization_code"
                    + "&login_scenario=normal"
                    + "&redirect_uri=" + URLEncoder.encode(REDIRECT_URI, "UTF-8")
                    + "&source=2"
                    + "&client_secret=" + CLIENT_SECRET
                    + "&client_id=" + APP_ID;

            String resp = httpPost(CONNECT_BASE + "/oauth/token/exchange", body,
                    "application/x-www-form-urlencoded", null);
            JSONObject json = new JSONObject(resp);
            capturedAccessToken = json.optString("access_token", "");
            capturedOpenId = json.optString("open_id", "");

            if (!capturedAccessToken.isEmpty()) {
                log("[Exchange] OK: open_id=" + capturedOpenId.substring(0, Math.min(16, capturedOpenId.length())) + "...");
                mainHandler.post(this::onTokensCaptured);
            } else {
                log("[Exchange] Failed: " + resp.substring(0, Math.min(200, resp.length())));
            }
        } catch (Exception e) {
            log("[Exchange] Error: " + e.getMessage());
        }
    }

    // ── Game API calls ──

    void doItopAndUsecode(String accessToken, String openId) throws Exception {
        // ITOP Login
        String ts = String.valueOf(System.currentTimeMillis() / 1000);
        String seqId = GAMEID + "-auto-" + ts;

        JSONObject itopBody = new JSONObject();
        itopBody.put("openid", openId);
        itopBody.put("token", accessToken);
        itopBody.put("channelid", Integer.parseInt(CHANNELID));
        itopBody.put("gameid", Integer.parseInt(GAMEID));
        itopBody.put("os", 1);
        itopBody.put("lang", "");
        itopBody.put("seq", seqId);
        itopBody.put("ts", ts);

        String itopParams = "channelid=" + CHANNELID + "&encrypt=0&gameid=" + GAMEID
                + "&lang=&os=1&seq=" + seqId + "&ts=" + ts + "&version=null";

        log("[ITOP] Login...");
        String itopResp = httpPost(ITOP_BASE + "/v2/auth/login?" + itopParams,
                itopBody.toString(), "application/json", "itop.kg.garena.vn");
        JSONObject itopJson = new JSONObject(itopResp);

        int ret = itopJson.optInt("ret", -1);
        if (ret != 0) {
            log("[ITOP] Error: ret=" + ret + " msg=" + itopJson.optString("msg", ""));
            return;
        }

        JSONObject tokenInfo = itopJson.optJSONObject("token_info");
        String aovToken, gameOpenId, gameToken;
        if (tokenInfo != null) {
            aovToken = tokenInfo.optString("aov_token", itopJson.optString("aov_token", ""));
            gameOpenId = itopJson.optString("openid", tokenInfo.optString("openid", ""));
            gameToken = tokenInfo.optString("game_token", itopJson.optString("game_token", ""));
        } else {
            aovToken = itopJson.optString("aov_token", "");
            gameOpenId = itopJson.optString("openid", "");
            gameToken = itopJson.optString("game_token", "");
        }
        log("[ITOP] OK: GameOpenId=" + gameOpenId.substring(0, Math.min(16, gameOpenId.length())) + "...");

        // getstartupdata
        Thread.sleep(1000);
        log("[AOV] getstartupdata...");
        JSONObject startupBody = new JSONObject();
        startupBody.put("deviceId", md5(gameOpenId));
        startupBody.put("lastLoginTime", 0);
        startupBody.put("name", "Player");
        startupBody.put("headUrl", "");
        startupBody.put("headFrameId", 0);

        try {
            String startupResp = httpPostAov(
                    AOV_CLOUD + "/vn_online/" + usecodeEventPath + "/getstartupdata",
                    startupBody.toString(), aovToken, gameOpenId, gameToken);
            JSONObject startupJson = new JSONObject(startupResp);
            int sCode = startupJson.optInt("code", -1);
            String sMsg = startupJson.optString("msg", "");
            if (sCode == 0) {
                log("[AOV] Session OK");
            } else if (sCode == 999 || sMsg.toLowerCase().contains("expired") || sMsg.toLowerCase().contains("token")) {
                log("[AOV] Token het han: " + sMsg);
                return;
            } else {
                log("[AOV] startup code=" + sCode + ": " + sMsg);
            }
        } catch (Exception e) {
            log("[AOV] startup error: " + e.getMessage());
        }

        // usecode
        Thread.sleep(1000);
        log("[AOV] usecode: " + inviteCode);
        JSONObject useBody = new JSONObject();
        useBody.put("invitationCode", inviteCode);

        String useResp = httpPostAov(
                AOV_CLOUD + "/vn_online/" + usecodeEventPath + "/usecode",
                useBody.toString(), aovToken, gameOpenId, gameToken);
        JSONObject useJson = new JSONObject(useResp);
        int uCode = useJson.optInt("code", -1);
        String uMsg = useJson.optString("msg", "");

        if (uCode == 0) {
            log("[+] THANH CONG! " + uMsg);
        } else {
            log("[!] usecode code=" + uCode + ": " + uMsg);
        }
    }

    // ── HTTP helpers ──

    String httpPost(String urlStr, String body, String contentType, String host) throws Exception {
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("Content-Type", contentType);
        if (host != null) conn.setRequestProperty("Host", host);
        conn.setRequestProperty("User-Agent",
                "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)");

        try (OutputStream os = conn.getOutputStream()) {
            os.write(body.getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
        BufferedReader br = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = br.readLine()) != null) sb.append(line);
        br.close();
        return sb.toString();
    }

    String httpPostAov(String urlStr, String body, String aovToken, String gameOpenId, String gameToken) throws Exception {
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("Host", "aovcloud.garena.com");
        conn.setRequestProperty("User-Agent", UNITY_UA);
        conn.setRequestProperty("X-Unity-Version", "2022.3.5f1");
        conn.setRequestProperty("aov_token", aovToken);
        conn.setRequestProperty("GameOpenId", gameOpenId);
        conn.setRequestProperty("gameToken", gameToken);
        conn.setRequestProperty("channel", "1");
        conn.setRequestProperty("platId", "1");
        conn.setRequestProperty("partition", PARTITION);
        conn.setRequestProperty("areaId", AREA_ID);
        conn.setRequestProperty("lang", "VN");
        conn.setRequestProperty("version", "0.0.6");
        conn.setRequestProperty("gmTimeStamp", String.valueOf(System.currentTimeMillis() / 1000));

        JSONObject userinfo = new JSONObject();
        userinfo.put("uin", gameOpenId);
        userinfo.put("areaID", AREA_ID);
        userinfo.put("roleID", gameOpenId);
        userinfo.put("platform", "1");
        userinfo.put("accType", "Guest");
        userinfo.put("partitionID", PARTITION);
        conn.setRequestProperty("userinfo", userinfo.toString());

        try (OutputStream os = conn.getOutputStream()) {
            os.write(body.getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
        BufferedReader br = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = br.readLine()) != null) sb.append(line);
        br.close();
        return sb.toString();
    }

    // ── Utility ──

    String md5(String input) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) sb.append(String.format("%02x", b & 0xff));
            return sb.toString();
        } catch (Exception e) {
            return input;
        }
    }

    void log(String msg) {
        mainHandler.post(() -> {
            tvLog.append(msg + "\n");
            scrollLog.post(() -> scrollLog.fullScroll(View.FOCUS_DOWN));
        });
    }

    void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    void toggleWebView() {
        webVisible = !webVisible;
        webView.setVisibility(webVisible ? View.VISIBLE : View.GONE);
        btnToggleWeb.setText(webVisible ? "AN WEB" : "WEB");
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        running = false;
        executor.shutdownNow();
    }
}
