package com.zg.luainjector;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.app.Notification;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.view.animation.OvershootInterpolator;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

import java.lang.reflect.Constructor;
import java.util.List;

public class FloatingMenuService extends Service {

    private WindowManager windowManager;
    private View floatingButton;
    private View menuContainer;
    private WindowManager.LayoutParams buttonParams;
    private WindowManager.LayoutParams menuParams;

    private boolean isMenuVisible = false;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private EditText etScript;
    private TextView tvStatus;
    private View statusDot;
    private LinearLayout scriptsList;
    private LinearLayout editorContent;
    private LinearLayout scriptsContent;
    private LinearLayout settingsContent;
    private TextView tabEditor;
    private TextView tabScripts;
    private TextView tabSettings;

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        startForegroundCompat();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        createFloatingButton();
        createFloatingMenu();
        startPulseAnimation();
    }

    private void startForegroundCompat() {
        try {
            Class<?> channelClass = Class.forName("android.app.NotificationChannel");
            Constructor<?> ctor = channelClass.getConstructor(String.class, CharSequence.class, int.class);
            Object channel = ctor.newInstance("zg_channel", "ZG Injector", 2);
            Object nm = getSystemService("notification");
            nm.getClass().getMethod("createNotificationChannel", channelClass).invoke(nm, channel);
        } catch (Exception ignored) {}

        Notification notification;
        try {
            Constructor<Notification.Builder> ctor =
                    Notification.Builder.class.getConstructor(Context.class, String.class);
            notification = ctor.newInstance(this, "zg_channel")
                    .setContentTitle("ZG Lua Injector")
                    .setContentText("Running")
                    .setSmallIcon(android.R.drawable.ic_menu_edit)
                    .build();
        } catch (Exception e) {
            notification = new Notification.Builder(this)
                    .setContentTitle("ZG Lua Injector")
                    .setContentText("Running")
                    .setSmallIcon(android.R.drawable.ic_menu_edit)
                    .build();
        }
        startForeground(1, notification);
    }

    private int dp(int val) {
        return (int) (val * getResources().getDisplayMetrics().density);
    }

    private int getOverlayType() {
        try {
            return WindowManager.LayoutParams.class.getField("TYPE_APPLICATION_OVERLAY").getInt(null);
        } catch (Exception e) {
            return WindowManager.LayoutParams.TYPE_PHONE;
        }
    }

    private void createFloatingButton() {
        TextView fab = new TextView(this);
        fab.setText("⚡");
        fab.setTextSize(24);
        fab.setGravity(Gravity.CENTER);

        GradientDrawable fabBg = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF6C63FF, 0xFF9D4EDD});
        fabBg.setShape(GradientDrawable.OVAL);
        fabBg.setStroke(dp(2), 0x60FFFFFF);
        fab.setBackground(fabBg);

        floatingButton = fab;

        buttonParams = new WindowManager.LayoutParams(
                dp(56), dp(56),
                getOverlayType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);
        buttonParams.gravity = Gravity.TOP | Gravity.START;
        buttonParams.x = dp(16);
        buttonParams.y = dp(200);

        windowManager.addView(floatingButton, buttonParams);
        setupButtonTouch();
    }

    private void setupButtonTouch() {
        floatingButton.setOnTouchListener(new View.OnTouchListener() {
            float initX, initY, touchX, touchY;
            boolean dragging;
            long downTime;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initX = buttonParams.x;
                        initY = buttonParams.y;
                        touchX = e.getRawX();
                        touchY = e.getRawY();
                        dragging = false;
                        downTime = System.currentTimeMillis();
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        float dx = e.getRawX() - touchX;
                        float dy = e.getRawY() - touchY;
                        if (Math.abs(dx) > 10 || Math.abs(dy) > 10) dragging = true;
                        if (dragging) {
                            buttonParams.x = (int) (initX + dx);
                            buttonParams.y = (int) (initY + dy);
                            try { windowManager.updateViewLayout(floatingButton, buttonParams); } catch (Exception ex) {}
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!dragging && System.currentTimeMillis() - downTime < 300) {
                            toggleMenu();
                        } else if (dragging) {
                            snapToEdge();
                        }
                        return true;
                }
                return false;
            }
        });
    }

    private void snapToEdge() {
        final int sw = getResources().getDisplayMetrics().widthPixels;
        final int target = buttonParams.x < sw / 2 ? dp(4) : sw - dp(60);
        ValueAnimator anim = ValueAnimator.ofInt(buttonParams.x, target);
        anim.setDuration(300);
        anim.setInterpolator(new OvershootInterpolator(1.5f));
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator a) {
                buttonParams.x = (Integer) a.getAnimatedValue();
                try { windowManager.updateViewLayout(floatingButton, buttonParams); } catch (Exception e) {}
            }
        });
        anim.start();
    }

    private void createFloatingMenu() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);

        GradientDrawable rootBg = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xE61A1A2E, 0xF016213E, 0xF00F3460});
        rootBg.setCornerRadius(dp(20));
        rootBg.setStroke(dp(1), 0x406C63FF);
        root.setBackground(rootBg);

        root.addView(createTitleBar());
        root.addView(createTabBar());

        editorContent = createEditorTab();
        root.addView(editorContent);

        scriptsContent = createScriptsTab();
        scriptsContent.setVisibility(View.GONE);
        root.addView(scriptsContent);

        settingsContent = createSettingsTab();
        settingsContent.setVisibility(View.GONE);
        root.addView(settingsContent);

        root.addView(createStatusBar());

        menuContainer = root;

        menuParams = new WindowManager.LayoutParams(
                dp(340),
                WindowManager.LayoutParams.WRAP_CONTENT,
                getOverlayType(),
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT);
        menuParams.gravity = Gravity.TOP | Gravity.START;
        menuParams.x = dp(20);
        menuParams.y = dp(100);
    }

    private View createTitleBar() {
        FrameLayout bar = new FrameLayout(this);
        bar.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(44)));

        GradientDrawable barBg = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{0xFF6C63FF, 0xFF9D4EDD});
        float r = dp(20);
        barBg.setCornerRadii(new float[]{r, r, r, r, 0, 0, 0, 0});
        bar.setBackground(barBg);

        TextView title = new TextView(this);
        title.setText("⚡ ZG Executor");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(14);
        title.setTypeface(null, Typeface.BOLD);
        FrameLayout.LayoutParams titleLp = new FrameLayout.LayoutParams(-2, -2);
        titleLp.gravity = Gravity.CENTER_VERTICAL | Gravity.START;
        titleLp.leftMargin = dp(14);
        bar.addView(title, titleLp);

        LinearLayout btns = new LinearLayout(this);
        btns.setOrientation(LinearLayout.HORIZONTAL);
        btns.setGravity(Gravity.CENTER_VERTICAL);
        FrameLayout.LayoutParams btnsLp = new FrameLayout.LayoutParams(-2, -2);
        btnsLp.gravity = Gravity.CENTER_VERTICAL | Gravity.END;
        btnsLp.rightMargin = dp(8);

        TextView btnMin = createCircleButton("—", 0x30FFFFFF, 0xFFFFFFFF);
        btnMin.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { hideMenu(); }
        });
        btns.addView(btnMin);

        TextView btnClose = createCircleButton("✕", 0x30FFFFFF, 0xFFFF6584);
        LinearLayout.LayoutParams clLp = new LinearLayout.LayoutParams(dp(28), dp(28));
        clLp.leftMargin = dp(4);
        btnClose.setLayoutParams(clLp);
        btnClose.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { hideMenu(); stopSelf(); }
        });
        btns.addView(btnClose);

        bar.addView(btns, btnsLp);

        bar.setOnTouchListener(new View.OnTouchListener() {
            float ix, iy, tx, ty;
            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        ix = menuParams.x; iy = menuParams.y;
                        tx = e.getRawX(); ty = e.getRawY();
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        menuParams.x = (int) (ix + e.getRawX() - tx);
                        menuParams.y = (int) (iy + e.getRawY() - ty);
                        try { windowManager.updateViewLayout(menuContainer, menuParams); } catch (Exception ex) {}
                        return true;
                }
                return false;
            }
        });

        return bar;
    }

    private TextView createCircleButton(String text, int bgColor, int textColor) {
        TextView btn = new TextView(this);
        btn.setText(text);
        btn.setTextSize(12);
        btn.setTextColor(textColor);
        btn.setGravity(Gravity.CENTER);
        GradientDrawable bg = new GradientDrawable();
        bg.setShape(GradientDrawable.OVAL);
        bg.setColor(bgColor);
        btn.setBackground(bg);
        btn.setLayoutParams(new LinearLayout.LayoutParams(dp(28), dp(28)));
        return btn;
    }

    private View createTabBar() {
        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, dp(36));
        lp.setMargins(dp(10), dp(8), dp(10), 0);
        tabs.setLayoutParams(lp);

        tabEditor = createTab("📝 Editor", true);
        tabScripts = createTab("📂 Scripts", false);
        tabSettings = createTab("⚙ Settings", false);

        View.OnClickListener tabClick = new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (v == tabEditor) switchTab(0);
                else if (v == tabScripts) switchTab(1);
                else if (v == tabSettings) switchTab(2);
            }
        };

        tabEditor.setOnClickListener(tabClick);
        tabScripts.setOnClickListener(tabClick);
        tabSettings.setOnClickListener(tabClick);

        tabs.addView(tabEditor);
        tabs.addView(tabScripts);
        tabs.addView(tabSettings);

        return tabs;
    }

    private TextView createTab(String text, boolean selected) {
        TextView tab = new TextView(this);
        tab.setText(text);
        tab.setTextSize(12);
        tab.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -1, 1f);
        lp.rightMargin = dp(4);
        tab.setLayoutParams(lp);
        updateTabStyle(tab, selected);
        return tab;
    }

    private void updateTabStyle(TextView tab, boolean selected) {
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(dp(8));
        bg.setColor(selected ? 0x406C63FF : 0x00000000);
        tab.setBackground(bg);
        tab.setTextColor(selected ? 0xFFEAEAEA : 0xFFA0A0B0);
    }

    private void switchTab(int index) {
        updateTabStyle(tabEditor, index == 0);
        updateTabStyle(tabScripts, index == 1);
        updateTabStyle(tabSettings, index == 2);
        editorContent.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        scriptsContent.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        settingsContent.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        if (index == 1) loadScriptsList();
    }

    private LinearLayout createEditorTab() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(10), dp(10), dp(10), dp(10));

        etScript = new EditText(this);
        etScript.setHint("-- Paste your Lua script here...\n-- Example:\nprint(\"Hello from ZG!\")");
        etScript.setHintTextColor(0xFF405060);
        etScript.setTextColor(0xFF00E676);
        etScript.setTextSize(12);
        etScript.setTypeface(Typeface.MONOSPACE);
        etScript.setGravity(Gravity.TOP | Gravity.START);
        etScript.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        etScript.setPadding(dp(12), dp(12), dp(12), dp(12));
        etScript.setMinLines(8);
        etScript.setMaxLines(12);

        GradientDrawable editorBg = new GradientDrawable();
        editorBg.setColor(0xCC0A0A1A);
        editorBg.setCornerRadius(dp(12));
        editorBg.setStroke(dp(1), 0x306C63FF);
        etScript.setBackground(editorBg);

        layout.addView(etScript, new LinearLayout.LayoutParams(-1, dp(180)));

        LinearLayout btnRow = new LinearLayout(this);
        btnRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams rowLp = new LinearLayout.LayoutParams(-1, -2);
        rowLp.topMargin = dp(8);
        btnRow.setLayoutParams(rowLp);

        btnRow.addView(createActionButton("⚡ INJECT",
                new int[]{0xFF6C63FF, 0xFF9D4EDD}, 0xFFFFFFFF, new View.OnClickListener() {
                    @Override public void onClick(View v) {
                        String s = etScript.getText().toString().trim();
                        if (s.isEmpty()) { updateStatus("No script entered", false); return; }
                        ScriptManager.submitScript(s);
                        animBtn(v);
                        updateStatus("Injecting...", true);
                    }
                }));

        btnRow.addView(createActionButton("▶ RUN",
                new int[]{0xFF00E676, 0xFF00C853}, 0xFF1A1A2E, new View.OnClickListener() {
                    @Override public void onClick(View v) {
                        String s = etScript.getText().toString().trim();
                        if (s.isEmpty()) { updateStatus("No script entered", false); return; }
                        ScriptManager.submitScript(s);
                        animBtn(v);
                        updateStatus("Executing...", true);
                    }
                }));

        btnRow.addView(createActionButton("🗑 CLEAR",
                new int[]{0xFFFF6584, 0xFFFF4757}, 0xFFFFFFFF, new View.OnClickListener() {
                    @Override public void onClick(View v) {
                        etScript.setText("");
                        animBtn(v);
                        updateStatus("Cleared", true);
                    }
                }));

        layout.addView(btnRow);
        return layout;
    }

    private View createActionButton(String text, int[] gradient, int textColor, View.OnClickListener listener) {
        TextView btn = new TextView(this);
        btn.setText(text);
        btn.setTextSize(13);
        btn.setTextColor(textColor);
        btn.setTypeface(null, Typeface.BOLD);
        btn.setGravity(Gravity.CENTER);

        GradientDrawable bg = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT, gradient);
        bg.setCornerRadius(dp(12));
        btn.setBackground(bg);
        btn.setPadding(dp(8), dp(10), dp(8), dp(10));

        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(40), 1f);
        lp.rightMargin = dp(4);
        btn.setLayoutParams(lp);

        btn.setOnClickListener(listener);
        return btn;
    }

    private LinearLayout createScriptsTab() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(10), dp(10), dp(10), dp(10));

        ScrollView sv = new ScrollView(this);
        sv.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(220)));

        scriptsList = new LinearLayout(this);
        scriptsList.setOrientation(LinearLayout.VERTICAL);
        sv.addView(scriptsList);
        layout.addView(sv);

        return layout;
    }

    private void loadScriptsList() {
        scriptsList.removeAllViews();

        addScriptItem("Infinite Jump",
                "-- Infinite Jump\nlocal uis = game:GetService('UserInputService')\nlocal lp = game.Players.LocalPlayer\nuis.JumpRequest:Connect(function()\n    if lp.Character then\n        lp.Character:FindFirstChildOfClass('Humanoid'):ChangeState('Jumping')\n    end\nend)");

        addScriptItem("Speed Boost",
                "-- Speed Boost\nlocal lp = game.Players.LocalPlayer\nif lp.Character then\n    local hum = lp.Character:FindFirstChildOfClass('Humanoid')\n    if hum then hum.WalkSpeed = 50 end\nend");

        addScriptItem("ESP Players",
                "-- ESP Highlight\nfor _, v in pairs(game.Players:GetPlayers()) do\n    if v ~= game.Players.LocalPlayer and v.Character then\n        local h = Instance.new('Highlight', v.Character)\n        h.FillColor = Color3.fromRGB(255, 0, 0)\n        h.OutlineColor = Color3.fromRGB(255, 255, 0)\n    end\nend");

        addScriptItem("No Clip",
                "-- No Clip\nlocal lp = game.Players.LocalPlayer\nlocal noclip = true\ngame:GetService('RunService').Stepped:Connect(function()\n    if noclip and lp.Character then\n        for _, p in pairs(lp.Character:GetDescendants()) do\n            if p:IsA('BasePart') then p.CanCollide = false end\n        end\n    end\nend)");

        addScriptItem("Fly Script",
                "-- Fly\nlocal lp = game.Players.LocalPlayer\nlocal speed = 50\n-- Press E to toggle fly");

        List<String[]> saved = ScriptManager.getSavedScripts(this);
        for (int i = 0; i < saved.size(); i++) {
            String[] entry = saved.get(i);
            addScriptItem(entry[0], entry[1]);
        }
    }

    private void addScriptItem(final String name, final String script) {
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.HORIZONTAL);
        item.setGravity(Gravity.CENTER_VERTICAL);
        item.setPadding(dp(12), dp(10), dp(12), dp(10));

        GradientDrawable itemBg = new GradientDrawable();
        itemBg.setColor(0x200F3460);
        itemBg.setCornerRadius(dp(10));
        itemBg.setStroke(dp(1), 0x206C63FF);
        item.setBackground(itemBg);

        LinearLayout.LayoutParams itemLp = new LinearLayout.LayoutParams(-1, -2);
        itemLp.bottomMargin = dp(6);
        item.setLayoutParams(itemLp);

        TextView icon = new TextView(this);
        icon.setText("📜");
        icon.setTextSize(16);
        icon.setPadding(0, 0, dp(10), 0);
        item.addView(icon);

        TextView tvName = new TextView(this);
        tvName.setText(name);
        tvName.setTextColor(0xFFEAEAEA);
        tvName.setTextSize(13);
        tvName.setLayoutParams(new LinearLayout.LayoutParams(0, -2, 1f));
        item.addView(tvName);

        TextView btnPlay = new TextView(this);
        btnPlay.setText("▶");
        btnPlay.setTextSize(16);
        btnPlay.setTextColor(0xFF00E676);
        btnPlay.setPadding(dp(8), 0, 0, 0);
        item.addView(btnPlay);

        item.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                etScript.setText(script);
                switchTab(0);
                updateStatus("Loaded: " + name, true);
            }
        });

        scriptsList.addView(item);
    }

    private LinearLayout createSettingsTab() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(10), dp(10), dp(10), dp(10));

        TextView label1 = new TextView(this);
        label1.setText("Menu Opacity");
        label1.setTextColor(0xFFEAEAEA);
        label1.setTextSize(13);
        layout.addView(label1);

        SeekBar seek = new SeekBar(this);
        seek.setMax(100);
        seek.setProgress(90);
        LinearLayout.LayoutParams seekLp = new LinearLayout.LayoutParams(-1, -2);
        seekLp.topMargin = dp(4);
        seek.setLayoutParams(seekLp);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar sb, int progress, boolean user) {
                if (menuContainer != null) menuContainer.setAlpha(Math.max(0.3f, progress / 100f));
            }
            @Override public void onStartTrackingTouch(SeekBar sb) {}
            @Override public void onStopTrackingTouch(SeekBar sb) {}
        });
        layout.addView(seek);

        View spacer = new View(this);
        spacer.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(16)));
        layout.addView(spacer);

        TextView label2 = new TextView(this);
        label2.setText("Auto-attach on game load");
        label2.setTextColor(0xFFEAEAEA);
        label2.setTextSize(13);
        layout.addView(label2);

        View spacer2 = new View(this);
        spacer2.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(20)));
        layout.addView(spacer2);

        TextView ver = new TextView(this);
        ver.setText("v1.0.0 | ZG Lua Injector");
        ver.setTextColor(0xFF505060);
        ver.setTextSize(11);
        layout.addView(ver);

        return layout;
    }

    private View createStatusBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(14), dp(6), dp(14), dp(8));

        GradientDrawable barBg = new GradientDrawable();
        barBg.setColor(0x200F3460);
        float r = dp(20);
        barBg.setCornerRadii(new float[]{0, 0, 0, 0, r, r, r, r});
        bar.setBackground(barBg);

        statusDot = new View(this);
        statusDot.setLayoutParams(new LinearLayout.LayoutParams(dp(8), dp(8)));
        GradientDrawable dotBg = new GradientDrawable();
        dotBg.setShape(GradientDrawable.OVAL);
        dotBg.setColor(0xFF00E676);
        statusDot.setBackground(dotBg);
        bar.addView(statusDot);

        tvStatus = new TextView(this);
        tvStatus.setText("Ready");
        tvStatus.setTextColor(0xFF00E676);
        tvStatus.setTextSize(11);
        LinearLayout.LayoutParams sLp = new LinearLayout.LayoutParams(-2, -2);
        sLp.leftMargin = dp(8);
        tvStatus.setLayoutParams(sLp);
        bar.addView(tvStatus);

        return bar;
    }

    private void toggleMenu() {
        if (isMenuVisible) hideMenu();
        else showMenu();
    }

    private void showMenu() {
        if (isMenuVisible) return;
        isMenuVisible = true;
        menuParams.x = buttonParams.x;
        menuParams.y = buttonParams.y + dp(64);
        windowManager.addView(menuContainer, menuParams);

        menuContainer.setScaleX(0.5f);
        menuContainer.setScaleY(0.5f);
        menuContainer.setAlpha(0f);
        menuContainer.animate()
                .scaleX(1f).scaleY(1f).alpha(1f)
                .setDuration(300)
                .setInterpolator(new OvershootInterpolator(1.2f))
                .start();

        ScriptManager.setStatusListener(new ScriptManager.StatusListener() {
            @Override
            public void onStatusChanged(final String status) {
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        updateStatus(status, !status.contains("fail") && !status.contains("error"));
                    }
                });
            }
        });
    }

    private void hideMenu() {
        if (!isMenuVisible) return;
        menuContainer.animate()
                .scaleX(0.5f).scaleY(0.5f).alpha(0f)
                .setDuration(200)
                .setInterpolator(new AccelerateDecelerateInterpolator())
                .withEndAction(new Runnable() {
                    @Override
                    public void run() {
                        try { windowManager.removeView(menuContainer); } catch (Exception e) {}
                        isMenuVisible = false;
                    }
                })
                .start();
    }

    private void updateStatus(final String msg, final boolean ok) {
        handler.post(new Runnable() {
            @Override
            public void run() {
                tvStatus.setText(msg);
                int color = ok ? 0xFF00E676 : 0xFFFF5252;
                tvStatus.setTextColor(color);
                setDotColor(color);

                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        tvStatus.setText("Ready");
                        tvStatus.setTextColor(0xFF00E676);
                        setDotColor(0xFF00E676);
                    }
                }, 3000);
            }
        });
    }

    private void setDotColor(int color) {
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.OVAL);
        d.setColor(color);
        d.setSize(dp(8), dp(8));
        statusDot.setBackground(d);
    }

    private void animBtn(final View v) {
        v.animate().scaleX(0.9f).scaleY(0.9f).setDuration(100)
                .withEndAction(new Runnable() {
                    @Override
                    public void run() {
                        v.animate().scaleX(1f).scaleY(1f).setDuration(100).start();
                    }
                }).start();
    }

    private void startPulseAnimation() {
        ObjectAnimator sx = ObjectAnimator.ofFloat(floatingButton, "scaleX", 1f, 1.15f, 1f);
        ObjectAnimator sy = ObjectAnimator.ofFloat(floatingButton, "scaleY", 1f, 1.15f, 1f);
        sx.setDuration(2000); sy.setDuration(2000);
        sx.setRepeatCount(ValueAnimator.INFINITE);
        sy.setRepeatCount(ValueAnimator.INFINITE);
        sx.setInterpolator(new AccelerateDecelerateInterpolator());
        sy.setInterpolator(new AccelerateDecelerateInterpolator());
        sx.start(); sy.start();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        try { if (floatingButton != null) windowManager.removeView(floatingButton); } catch (Exception e) {}
        try { if (isMenuVisible && menuContainer != null) windowManager.removeView(menuContainer); } catch (Exception e) {}
    }
}
