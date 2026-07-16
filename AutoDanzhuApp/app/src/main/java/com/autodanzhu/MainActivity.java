package com.autodanzhu;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.ConsoleMessage;
import android.webkit.CookieManager;
import android.webkit.CookieSyncManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {

    private static final String APP_ID = "100054";
    private static final String CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515";
    private static final String REDIRECT_URI = "gop100054://auth/";
    private static final String CONNECT_BASE = "https://100054.connect.garena.com";
    private static final String ITOP_BASE = "https://itop.kg.garena.vn";
    private static final String AOV_CLOUD = "https://aovcloud.garena.com";
    private static final String GAMEID = "1137";
    private static final String CHANNELID = "10";
    private static final String PARTITION = "1011";
    private static final String AREA_ID = "1";
    private static final String UNITY_UA = "UnityPlayer/2022.3.5f1 (UnityWebRequest/1.0, libcurl/8.1.1-DEV)";
    private static final String SDK_UA = "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)";

    private static final String LOGIN_URL = CONNECT_BASE + "/universal/oauth?"
            + "redirect_uri=" + Uri.encode(REDIRECT_URI)
            + "&response_type=code&client_id=" + APP_ID
            + "&login_scenario=normal&locale=vi-VN";

    private EditText etFilePath;
    private EditText etCode;
    private Button btnStart;
    private Button btnStop;
    private Button btnToggleWeb;
    private TextView tvStatus;
    private TextView tvLog;
    private ScrollView scrollLog;
    private WebView webView;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private List<String[]> accounts = new ArrayList<String[]>();
    private int currentIndex = 0;
    private String inviteCode = "";
    private volatile boolean running = false;
    private boolean webVisible = false;
    private String eventPath = "danzhu";

    private volatile String capturedCode = null;
    private volatile String capturedAccessToken = null;
    private volatile String capturedOpenId = null;
    private volatile boolean tokenProcessing = false;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etFilePath = (EditText) findViewById(R.id.etFilePath);
        etCode = (EditText) findViewById(R.id.etCode);
        btnStart = (Button) findViewById(R.id.btnStart);
        btnStop = (Button) findViewById(R.id.btnStop);
        btnToggleWeb = (Button) findViewById(R.id.btnToggleWeb);
        tvStatus = (TextView) findViewById(R.id.tvStatus);
        tvLog = (TextView) findViewById(R.id.tvLog);
        scrollLog = (ScrollView) findViewById(R.id.scrollLog);
        webView = (WebView) findViewById(R.id.webView);

        setupWebView();

        btnStart.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startProcessing();
            }
        });

        btnStop.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                stopProcessing();
            }
        });

        btnToggleWeb.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                toggleWebView();
            }
        });
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
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
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url != null && url.startsWith("gop100054://")) {
                    log("[WebView] Redirect: " + url.substring(0, Math.min(url.length(), 80)));
                    parseRedirectUrl(url);
                    return true;
                }
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (url != null && url.contains("connect.garena.com") && running) {
                    log("[WebView] Page loaded");
                    injectHooks();
                    mainHandler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            autoFillAndSubmit();
                        }
                    }, 2500);
                }
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                log("[WebView] Error: " + description);
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage cm) {
                if (cm.message() != null && cm.message().startsWith("[AD]")) {
                    log("[JS] " + cm.message());
                }
                return true;
            }
        });
    }

    // ── JS injection ──

    private void injectHooks() {
        String js = "(function(){"
            + "if(window.__adH)return;window.__adH=true;"
            + "console.log('[AD] Hooks OK');"
            + "var oO=XMLHttpRequest.prototype.open;"
            + "var oS=XMLHttpRequest.prototype.send;"
            + "XMLHttpRequest.prototype.open=function(m,u){"
            + "this._u=u;return oO.apply(this,arguments);};"
            + "XMLHttpRequest.prototype.send=function(){"
            + "var s=this;"
            + "this.addEventListener('load',function(){"
            + "try{"
            + "var u=s._u||'';"
            + "if(u.indexOf('/oauth/token/grant')!==-1||u.indexOf('/oauth/token/exchange')!==-1){"
            + "console.log('[AD] Token: '+u);"
            + "AutoDanzhu.onToken(u,s.responseText,s.status);"
            + "}else if(u.indexOf('/api/login')!==-1){"
            + "console.log('[AD] Login: '+s.status);"
            + "AutoDanzhu.onLogin(s.responseText,s.status);"
            + "}else if(u.indexOf('/api/prelogin')!==-1){"
            + "console.log('[AD] Prelogin: '+s.status);"
            + "}"
            + "}catch(e){console.log('[AD] Err: '+e);}"
            + "});"
            + "return oS.apply(this,arguments);};"
            + "})();";
        webView.evaluateJavascript(js, null);
    }

    private void autoFillAndSubmit() {
        if (!running || currentIndex >= accounts.size()) return;
        String[] acc = accounts.get(currentIndex);
        String user = acc[0].replace("\\", "\\\\").replace("'", "\\'");
        String pass = acc[1].replace("\\", "\\\\").replace("'", "\\'");

        String js = "(function(){"
            + "var r=0;"
            + "function sv(el,v){"
            + "var s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
            + "s.call(el,v);"
            + "el.dispatchEvent(new Event('input',{bubbles:true}));"
            + "el.dispatchEvent(new Event('change',{bubbles:true}));"
            + "}"
            + "function go(){"
            + "var p=document.querySelector('input[type=\"password\"]');"
            + "if(!p){r++;if(r<20){console.log('[AD] Wait pwd field '+r);setTimeout(go,800);}return;}"
            + "var ins=document.querySelectorAll('input');"
            + "var ui=null;"
            + "for(var i=0;i<ins.length;i++){"
            + "if(ins[i].type!=='password'&&ins[i].type!=='hidden'&&ins[i].type!=='checkbox'){ui=ins[i];break;}"
            + "}"
            + "if(!ui){console.log('[AD] No user field');return;}"
            + "console.log('[AD] Fill: " + user + "');"
            + "sv(ui,'" + user + "');"
            + "sv(p,'" + pass + "');"
            + "setTimeout(function(){"
            + "var bs=document.querySelectorAll('button');"
            + "for(var i=0;i<bs.length;i++){"
            + "var t=(bs[i].textContent||'').toLowerCase();"
            + "if(t.indexOf('log')!==-1||t.indexOf('sign')!==-1||t.indexOf('ng nh')!==-1||t.indexOf('dang nhap')!==-1){"
            + "console.log('[AD] Click: '+bs[i].textContent);"
            + "bs[i].click();return;"
            + "}"
            + "}"
            + "var pr=document.querySelector('button.primary,button[type=\"submit\"]');"
            + "if(pr){console.log('[AD] Click primary');pr.click();return;}"
            + "if(bs.length>0){bs[0].click();}"
            + "},500);"
            + "}"
            + "go();"
            + "})();";
        webView.evaluateJavascript(js, null);
    }

    // ── JS Interface ──

    private class WebBridge {
        @JavascriptInterface
        public void onToken(final String url, final String body, final int status) {
            log("[Token] " + url.substring(url.lastIndexOf('/') + 1) + " s=" + status);
            try {
                JSONObject j = new JSONObject(body);
                if (url.contains("token/exchange")) {
                    capturedAccessToken = j.optString("access_token", "");
                    capturedOpenId = j.optString("open_id", "");
                    if (capturedAccessToken.length() > 0) {
                        log("[Token] Got access_token + open_id!");
                        mainHandler.post(new Runnable() {
                            @Override
                            public void run() { onTokensCaptured(); }
                        });
                    }
                } else if (url.contains("token/grant")) {
                    String code = j.optString("code", "");
                    if (code.length() > 0) {
                        capturedCode = code;
                        log("[Token] Got auth code");
                    }
                }
            } catch (Exception e) {
                log("[Token] Err: " + e.getMessage());
            }
        }

        @JavascriptInterface
        public void onLogin(final String body, final int status) {
            try {
                JSONObject j = new JSONObject(body);
                if (j.has("error")) {
                    log("[Login] Error: " + j.optString("error"));
                } else {
                    log("[Login] OK: " + j.optString("username", "") + " uid=" + j.optInt("uid", 0));
                }
            } catch (Exception e) {
                log("[Login] Err: " + e.getMessage());
            }
        }
    }

    private void parseRedirectUrl(String url) {
        try {
            Uri uri = Uri.parse(url);
            String code = uri.getQueryParameter("code");
            if (code != null && code.length() > 0) {
                capturedCode = code;
                log("[Redirect] Got auth code");
                new Thread(new Runnable() {
                    @Override
                    public void run() { doTokenExchange(); }
                }).start();
            }
            String token = uri.getQueryParameter("access_token");
            if (token != null && token.length() > 0) {
                capturedAccessToken = token;
                capturedOpenId = uri.getQueryParameter("open_id");
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() { onTokensCaptured(); }
                });
            }
        } catch (Exception e) {
            log("[Redirect] Err: " + e.getMessage());
        }
    }

    // ── Processing ──

    private void startProcessing() {
        String filePath = etFilePath.getText().toString().trim();
        inviteCode = etCode.getText().toString().trim();

        if (filePath.length() == 0) {
            toast("Nhap duong dan file accounts");
            return;
        }
        if (inviteCode.length() == 0) {
            toast("Nhap ma moi");
            return;
        }

        accounts.clear();
        BufferedReader reader = null;
        try {
            if (filePath.startsWith("content://")) {
                InputStream is = getContentResolver().openInputStream(Uri.parse(filePath));
                reader = new BufferedReader(new InputStreamReader(is, "UTF-8"));
            } else {
                reader = new BufferedReader(new FileReader(filePath));
            }
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.length() == 0 || line.startsWith("#")) continue;
                String[] parts = line.split(":", 2);
                if (parts.length == 2 && parts[0].length() > 0 && parts[1].length() > 0) {
                    accounts.add(parts);
                }
            }
        } catch (Exception e) {
            log("Loi doc file: " + e.getMessage());
            toast("Khong doc duoc file");
            return;
        } finally {
            if (reader != null) {
                try { reader.close(); } catch (Exception ignored) {}
            }
        }

        if (accounts.isEmpty()) {
            toast("File khong co account (format: account:password)");
            return;
        }

        log("=== BAT DAU ===");
        log("Accounts: " + accounts.size() + " | Code: " + inviteCode);

        running = true;
        currentIndex = 0;
        btnStart.setEnabled(false);
        btnStop.setEnabled(true);
        processNextAccount();
    }

    private void stopProcessing() {
        running = false;
        log("=== DA DUNG ===");
        btnStart.setEnabled(true);
        btnStop.setEnabled(false);
        tvStatus.setText("Da dung");
    }

    @SuppressWarnings("deprecation")
    private void processNextAccount() {
        if (!running || currentIndex >= accounts.size()) {
            log("\n=== XONG " + accounts.size() + " ACCOUNTS ===");
            stopProcessing();
            return;
        }

        String[] acc = accounts.get(currentIndex);
        String label = (currentIndex + 1) + "/" + accounts.size();
        log("\n[" + label + "] Account: " + acc[0]);
        tvStatus.setText(acc[0] + " (" + label + ")");

        capturedCode = null;
        capturedAccessToken = null;
        capturedOpenId = null;
        tokenProcessing = false;

        CookieSyncManager.createInstance(this);
        CookieManager cm = CookieManager.getInstance();
        cm.removeAllCookie();

        webView.clearCache(true);
        webView.clearHistory();

        mainHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                log("[WebView] Loading...");
                webView.loadUrl(LOGIN_URL);
            }
        }, 500);

        mainHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (running && capturedAccessToken == null && capturedCode == null) {
                    log("[!] Timeout 60s - captcha? Bam WEB de xem.");
                    if (!webVisible) toggleWebView();
                }
            }
        }, 60000);
    }

    private void onTokensCaptured() {
        if (!running) return;
        if (capturedAccessToken == null || capturedAccessToken.length() == 0) return;
        if (tokenProcessing) return;
        tokenProcessing = true;

        log("[+] Tokens OK! ITOP + usecode...");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    doItopAndUsecode(capturedAccessToken, capturedOpenId);
                } catch (Exception e) {
                    log("[!] Error: " + e.getMessage());
                }
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        currentIndex++;
                        if (running) {
                            mainHandler.postDelayed(new Runnable() {
                                @Override
                                public void run() { processNextAccount(); }
                            }, 2000);
                        }
                    }
                });
            }
        }).start();
    }

    private void doTokenExchange() {
        if (capturedCode == null || capturedCode.length() == 0) return;
        try {
            log("[Exchange] Requesting...");
            String body = "code=" + capturedCode
                    + "&grant_type=authorization_code"
                    + "&login_scenario=normal"
                    + "&redirect_uri=" + URLEncoder.encode(REDIRECT_URI, "UTF-8")
                    + "&source=2"
                    + "&client_secret=" + CLIENT_SECRET
                    + "&client_id=" + APP_ID;

            String resp = httpPost(CONNECT_BASE + "/oauth/token/exchange", body,
                    "application/x-www-form-urlencoded", null, SDK_UA);
            JSONObject j = new JSONObject(resp);
            capturedAccessToken = j.optString("access_token", "");
            capturedOpenId = j.optString("open_id", "");

            if (capturedAccessToken.length() > 0) {
                log("[Exchange] OK: open_id=" + safe(capturedOpenId, 16) + "...");
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() { onTokensCaptured(); }
                });
            } else {
                log("[Exchange] Failed: " + safe(resp, 200));
            }
        } catch (Exception e) {
            log("[Exchange] Err: " + e.getMessage());
        }
    }

    // ── Game APIs ──

    private void doItopAndUsecode(String accessToken, String openId) throws Exception {
        String ts = String.valueOf(System.currentTimeMillis() / 1000);
        String seq = GAMEID + "-auto-" + ts;

        JSONObject ib = new JSONObject();
        ib.put("openid", openId);
        ib.put("token", accessToken);
        ib.put("channelid", Integer.parseInt(CHANNELID));
        ib.put("gameid", Integer.parseInt(GAMEID));
        ib.put("os", 1);
        ib.put("lang", "");
        ib.put("seq", seq);
        ib.put("ts", ts);

        String qp = "channelid=" + CHANNELID + "&encrypt=0&gameid=" + GAMEID
                + "&lang=&os=1&seq=" + seq + "&ts=" + ts + "&version=null";

        log("[ITOP] Login...");
        String ir = httpPost(ITOP_BASE + "/v2/auth/login?" + qp,
                ib.toString(), "application/json", "itop.kg.garena.vn", SDK_UA);
        JSONObject ij = new JSONObject(ir);

        int ret = ij.optInt("ret", -1);
        if (ret != 0) {
            log("[ITOP] Error: ret=" + ret + " " + ij.optString("msg", ""));
            return;
        }

        JSONObject ti = ij.optJSONObject("token_info");
        String aovToken, goid, gtok;
        if (ti != null) {
            aovToken = ti.optString("aov_token", ij.optString("aov_token", ""));
            goid = ij.optString("openid", ti.optString("openid", ""));
            gtok = ti.optString("game_token", ij.optString("game_token", ""));
        } else {
            aovToken = ij.optString("aov_token", "");
            goid = ij.optString("openid", "");
            gtok = ij.optString("game_token", "");
        }
        log("[ITOP] OK: " + safe(goid, 16) + "...");

        Thread.sleep(1000);

        // getstartupdata
        log("[AOV] startup...");
        JSONObject sb = new JSONObject();
        sb.put("deviceId", md5(goid));
        sb.put("lastLoginTime", 0);
        sb.put("name", "Player");
        sb.put("headUrl", "");
        sb.put("headFrameId", 0);

        try {
            String sr = httpPostAov(AOV_CLOUD + "/vn_online/" + eventPath + "/getstartupdata",
                    sb.toString(), aovToken, goid, gtok);
            JSONObject sj = new JSONObject(sr);
            int sc = sj.optInt("code", -1);
            String sm = sj.optString("msg", "");
            if (sc == 0) {
                log("[AOV] Session OK");
            } else if (sc == 999 || sm.toLowerCase().contains("expired") || sm.toLowerCase().contains("token")) {
                log("[AOV] Token het han: " + sm);
                return;
            } else {
                log("[AOV] startup=" + sc + ": " + sm);
            }
        } catch (Exception e) {
            log("[AOV] startup err: " + e.getMessage());
        }

        Thread.sleep(1000);

        // usecode
        log("[AOV] usecode: " + inviteCode);
        JSONObject ub = new JSONObject();
        ub.put("invitationCode", inviteCode);

        String ur = httpPostAov(AOV_CLOUD + "/vn_online/" + eventPath + "/usecode",
                ub.toString(), aovToken, goid, gtok);
        JSONObject uj = new JSONObject(ur);
        int uc = uj.optInt("code", -1);
        String um = uj.optString("msg", "");

        if (uc == 0) {
            log("[+] THANH CONG! " + um);
        } else {
            log("[!] usecode=" + uc + ": " + um);
        }
    }

    // ── HTTP ──

    private String httpPost(String urlStr, String body, String contentType, String host, String ua) throws Exception {
        HttpURLConnection conn = null;
        OutputStream os = null;
        InputStream is = null;
        BufferedReader br = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            conn.setRequestProperty("Content-Type", contentType);
            if (host != null) conn.setRequestProperty("Host", host);
            if (ua != null) conn.setRequestProperty("User-Agent", ua);

            byte[] bytes = body.getBytes("UTF-8");
            os = conn.getOutputStream();
            os.write(bytes);
            os.flush();

            int code = conn.getResponseCode();
            is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
            br = new BufferedReader(new InputStreamReader(is, "UTF-8"));
            StringBuilder result = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) result.append(line);
            return result.toString();
        } finally {
            if (br != null) try { br.close(); } catch (Exception ignored) {}
            if (is != null) try { is.close(); } catch (Exception ignored) {}
            if (os != null) try { os.close(); } catch (Exception ignored) {}
            if (conn != null) conn.disconnect();
        }
    }

    private String httpPostAov(String urlStr, String body, String aovToken, String goid, String gtok) throws Exception {
        HttpURLConnection conn = null;
        OutputStream os = null;
        InputStream is = null;
        BufferedReader br = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setRequestProperty("Host", "aovcloud.garena.com");
            conn.setRequestProperty("User-Agent", UNITY_UA);
            conn.setRequestProperty("X-Unity-Version", "2022.3.5f1");
            conn.setRequestProperty("aov_token", aovToken);
            conn.setRequestProperty("GameOpenId", goid);
            conn.setRequestProperty("gameToken", gtok);
            conn.setRequestProperty("channel", "1");
            conn.setRequestProperty("platId", "1");
            conn.setRequestProperty("partition", PARTITION);
            conn.setRequestProperty("areaId", AREA_ID);
            conn.setRequestProperty("lang", "VN");
            conn.setRequestProperty("version", "0.0.6");
            conn.setRequestProperty("gmTimeStamp", String.valueOf(System.currentTimeMillis() / 1000));

            JSONObject ui = new JSONObject();
            ui.put("uin", goid);
            ui.put("areaID", AREA_ID);
            ui.put("roleID", goid);
            ui.put("platform", "1");
            ui.put("accType", "Guest");
            ui.put("partitionID", PARTITION);
            conn.setRequestProperty("userinfo", ui.toString());

            byte[] bytes = body.getBytes("UTF-8");
            os = conn.getOutputStream();
            os.write(bytes);
            os.flush();

            int code = conn.getResponseCode();
            is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
            br = new BufferedReader(new InputStreamReader(is, "UTF-8"));
            StringBuilder result = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) result.append(line);
            return result.toString();
        } finally {
            if (br != null) try { br.close(); } catch (Exception ignored) {}
            if (is != null) try { is.close(); } catch (Exception ignored) {}
            if (os != null) try { os.close(); } catch (Exception ignored) {}
            if (conn != null) conn.disconnect();
        }
    }

    // ── Util ──

    private String md5(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(input.getBytes("UTF-8"));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < digest.length; i++) {
                sb.append(String.format("%02x", digest[i] & 0xff));
            }
            return sb.toString();
        } catch (Exception e) {
            return input;
        }
    }

    private String safe(String s, int max) {
        if (s == null) return "";
        return s.substring(0, Math.min(s.length(), max));
    }

    private void log(final String msg) {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                tvLog.append(msg + "\n");
                scrollLog.post(new Runnable() {
                    @Override
                    public void run() { scrollLog.fullScroll(View.FOCUS_DOWN); }
                });
            }
        });
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private void toggleWebView() {
        webVisible = !webVisible;
        webView.setVisibility(webVisible ? View.VISIBLE : View.GONE);
        btnToggleWeb.setText(webVisible ? "AN WEB" : "WEB");
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        running = false;
    }
}
