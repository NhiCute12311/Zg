package com.zg.luainjector;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.view.animation.OvershootInterpolator;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

public class FloatingMenuService extends Service {

    private WindowManager windowManager;
    private View floatingMenu;
    private View floatingButton;
    private WindowManager.LayoutParams menuParams;
    private WindowManager.LayoutParams buttonParams;

    private boolean isMenuVisible = false;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private EditText etScript;
    private TextView tvStatus;
    private View statusDot;
    private LinearLayout scriptsList;

    private static final String CHANNEL_ID = "zg_injector_channel";

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startForeground(1, buildNotification());

        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);

        createFloatingButton();
        createFloatingMenu();
        setupListeners();
        setupStatusListener();
        startPulseAnimation();
    }

    private void createNotificationChannel() {
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "ZG Injector", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Floating menu service");
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(channel);
    }

    private Notification buildNotification() {
        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("ZG Lua Injector")
                .setContentText("Running...")
                .setSmallIcon(android.R.drawable.ic_menu_edit)
                .build();
    }

    private void createFloatingButton() {
        floatingButton = createFabView();

        buttonParams = new WindowManager.LayoutParams(
                dpToPx(56),
                dpToPx(56),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT
        );
        buttonParams.gravity = Gravity.TOP | Gravity.START;
        buttonParams.x = dpToPx(16);
        buttonParams.y = dpToPx(200);

        windowManager.addView(floatingButton, buttonParams);

        setupDragForButton();
    }

    private View createFabView() {
        TextView fab = new TextView(this);
        fab.setText("⚡");
        fab.setTextSize(22);
        fab.setGravity(Gravity.CENTER);
        fab.setBackground(getDrawable(R.drawable.bg_floating_btn));
        fab.setElevation(dpToPx(8));
        return fab;
    }

    private void createFloatingMenu() {
        LayoutInflater inflater = LayoutInflater.from(this);
        floatingMenu = inflater.inflate(R.layout.layout_floating_menu, null);

        menuParams = new WindowManager.LayoutParams(
                dpToPx(340),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT
        );
        menuParams.gravity = Gravity.TOP | Gravity.START;
        menuParams.x = dpToPx(20);
        menuParams.y = dpToPx(100);

        etScript = floatingMenu.findViewById(R.id.etScript);
        tvStatus = floatingMenu.findViewById(R.id.tvStatus);
        statusDot = floatingMenu.findViewById(R.id.statusDot);
        scriptsList = floatingMenu.findViewById(R.id.scriptsList);

        setupDragForMenu();
    }

    private void setupListeners() {
        // Floating button click -> toggle menu
        floatingButton.setOnClickListener(v -> toggleMenu());

        // Minimize button
        floatingMenu.findViewById(R.id.btnMinimize).setOnClickListener(v -> hideMenu());

        // Close button
        floatingMenu.findViewById(R.id.btnClose).setOnClickListener(v -> {
            hideMenu();
            stopSelf();
        });

        // Inject button
        floatingMenu.findViewById(R.id.btnInject).setOnClickListener(v -> {
            String script = etScript.getText().toString().trim();
            if (script.isEmpty()) {
                updateStatus("No script entered", false);
                return;
            }
            ScriptManager.submitScript(script);
            animateButton(v);
            updateStatus("Injecting...", true);
        });

        // Execute button
        floatingMenu.findViewById(R.id.btnExecute).setOnClickListener(v -> {
            String script = etScript.getText().toString().trim();
            if (script.isEmpty()) {
                updateStatus("No script entered", false);
                return;
            }
            ScriptManager.submitScript(script);
            animateButton(v);
            updateStatus("Executing...", true);
        });

        // Clear button
        floatingMenu.findViewById(R.id.btnClear).setOnClickListener(v -> {
            etScript.setText("");
            animateButton(v);
            updateStatus("Cleared", true);
        });

        // Tab switching
        setupTabs();

        // Opacity seek bar
        SeekBar seekOpacity = floatingMenu.findViewById(R.id.seekOpacity);
        seekOpacity.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                float alpha = progress / 100f;
                floatingMenu.setAlpha(Math.max(0.3f, alpha));
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {}

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {}
        });
    }

    private void setupTabs() {
        View tabEditor = floatingMenu.findViewById(R.id.tabEditor);
        View tabScripts = floatingMenu.findViewById(R.id.tabScripts);
        View tabSettings = floatingMenu.findViewById(R.id.tabSettings);

        View editorContent = floatingMenu.findViewById(R.id.editorContent);
        View scriptsContent = floatingMenu.findViewById(R.id.scriptsContent);
        View settingsContent = floatingMenu.findViewById(R.id.settingsContent);

        View.OnClickListener tabClickListener = v -> {
            tabEditor.setBackgroundResource(R.drawable.bg_tab_unselected);
            tabScripts.setBackgroundResource(R.drawable.bg_tab_unselected);
            tabSettings.setBackgroundResource(R.drawable.bg_tab_unselected);
            ((TextView) tabEditor).setTextColor(Color.parseColor("#A0A0B0"));
            ((TextView) tabScripts).setTextColor(Color.parseColor("#A0A0B0"));
            ((TextView) tabSettings).setTextColor(Color.parseColor("#A0A0B0"));

            editorContent.setVisibility(View.GONE);
            scriptsContent.setVisibility(View.GONE);
            settingsContent.setVisibility(View.GONE);

            v.setBackgroundResource(R.drawable.bg_tab_selected);
            ((TextView) v).setTextColor(Color.parseColor("#EAEAEA"));

            if (v.getId() == R.id.tabEditor) {
                editorContent.setVisibility(View.VISIBLE);
            } else if (v.getId() == R.id.tabScripts) {
                scriptsContent.setVisibility(View.VISIBLE);
                loadScriptsList();
            } else if (v.getId() == R.id.tabSettings) {
                settingsContent.setVisibility(View.VISIBLE);
            }
        };

        tabEditor.setOnClickListener(tabClickListener);
        tabScripts.setOnClickListener(tabClickListener);
        tabSettings.setOnClickListener(tabClickListener);
    }

    private void loadScriptsList() {
        scriptsList.removeAllViews();

        addScriptPreset("Infinite Jump",
                "-- Infinite Jump\n" +
                "local uis = game:GetService('UserInputService')\n" +
                "local lp = game.Players.LocalPlayer\n" +
                "uis.JumpRequest:Connect(function()\n" +
                "    if lp.Character then\n" +
                "        lp.Character:FindFirstChildOfClass('Humanoid'):ChangeState('Jumping')\n" +
                "    end\n" +
                "end)");

        addScriptPreset("Speed Boost",
                "-- Speed Boost\n" +
                "local lp = game.Players.LocalPlayer\n" +
                "if lp.Character then\n" +
                "    local hum = lp.Character:FindFirstChildOfClass('Humanoid')\n" +
                "    if hum then hum.WalkSpeed = 50 end\n" +
                "end");

        addScriptPreset("ESP Players",
                "-- ESP Highlight\n" +
                "for _, v in pairs(game.Players:GetPlayers()) do\n" +
                "    if v ~= game.Players.LocalPlayer and v.Character then\n" +
                "        local h = Instance.new('Highlight', v.Character)\n" +
                "        h.FillColor = Color3.fromRGB(255, 0, 0)\n" +
                "        h.OutlineColor = Color3.fromRGB(255, 255, 0)\n" +
                "    end\n" +
                "end");

        List<String[]> saved = ScriptManager.getSavedScripts(this);
        for (String[] entry : saved) {
            addScriptPreset(entry[0], entry[1]);
        }
    }

    private void addScriptPreset(String name, String script) {
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.HORIZONTAL);
        item.setBackgroundResource(R.drawable.bg_script_item);
        item.setPadding(dpToPx(12), dpToPx(10), dpToPx(12), dpToPx(10));
        item.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout.LayoutParams itemParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        itemParams.bottomMargin = dpToPx(6);
        item.setLayoutParams(itemParams);

        TextView icon = new TextView(this);
        icon.setText("📜");
        icon.setTextSize(16);
        icon.setPadding(0, 0, dpToPx(10), 0);
        item.addView(icon);

        TextView tvName = new TextView(this);
        tvName.setText(name);
        tvName.setTextColor(Color.parseColor("#EAEAEA"));
        tvName.setTextSize(13);
        LinearLayout.LayoutParams nameParams = new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        tvName.setLayoutParams(nameParams);
        item.addView(tvName);

        TextView btnLoad = new TextView(this);
        btnLoad.setText("▶");
        btnLoad.setTextSize(16);
        btnLoad.setPadding(dpToPx(8), 0, 0, 0);
        item.addView(btnLoad);

        item.setOnClickListener(v -> {
            etScript.setText(script);
            floatingMenu.findViewById(R.id.tabEditor).performClick();
            updateStatus("Script loaded: " + name, true);
        });

        scriptsList.addView(item);
    }

    private void setupDragForButton() {
        floatingButton.setOnTouchListener(new View.OnTouchListener() {
            private float initialX, initialY;
            private float initialTouchX, initialTouchY;
            private boolean isDragging = false;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = buttonParams.x;
                        initialY = buttonParams.y;
                        initialTouchX = event.getRawX();
                        initialTouchY = event.getRawY();
                        isDragging = false;
                        return false;

                    case MotionEvent.ACTION_MOVE:
                        float dx = event.getRawX() - initialTouchX;
                        float dy = event.getRawY() - initialTouchY;

                        if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
                            isDragging = true;
                        }

                        if (isDragging) {
                            buttonParams.x = (int) (initialX + dx);
                            buttonParams.y = (int) (initialY + dy);
                            windowManager.updateViewLayout(floatingButton, buttonParams);
                            return true;
                        }
                        return false;

                    case MotionEvent.ACTION_UP:
                        if (isDragging) {
                            snapToEdge();
                            return true;
                        }
                        return false;
                }
                return false;
            }
        });
    }

    private void snapToEdge() {
        int screenWidth = getResources().getDisplayMetrics().widthPixels;
        int targetX = buttonParams.x < screenWidth / 2 ? dpToPx(4) : screenWidth - dpToPx(60);

        ValueAnimator animator = ValueAnimator.ofInt(buttonParams.x, targetX);
        animator.setDuration(300);
        animator.setInterpolator(new OvershootInterpolator(1.5f));
        animator.addUpdateListener(animation -> {
            buttonParams.x = (int) animation.getAnimatedValue();
            try {
                windowManager.updateViewLayout(floatingButton, buttonParams);
            } catch (Exception ignored) {}
        });
        animator.start();
    }

    private void setupDragForMenu() {
        View titleBar = floatingMenu.findViewById(R.id.titleBar);
        titleBar.setOnTouchListener(new View.OnTouchListener() {
            private float initialX, initialY;
            private float initialTouchX, initialTouchY;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = menuParams.x;
                        initialY = menuParams.y;
                        initialTouchX = event.getRawX();
                        initialTouchY = event.getRawY();
                        return true;

                    case MotionEvent.ACTION_MOVE:
                        menuParams.x = (int) (initialX + (event.getRawX() - initialTouchX));
                        menuParams.y = (int) (initialY + (event.getRawY() - initialTouchY));
                        try {
                            windowManager.updateViewLayout(floatingMenu, menuParams);
                        } catch (Exception ignored) {}
                        return true;
                }
                return false;
            }
        });
    }

    private void toggleMenu() {
        if (isMenuVisible) {
            hideMenu();
        } else {
            showMenu();
        }
    }

    private void showMenu() {
        if (isMenuVisible) return;
        isMenuVisible = true;

        menuParams.x = buttonParams.x;
        menuParams.y = buttonParams.y + dpToPx(64);
        windowManager.addView(floatingMenu, menuParams);

        floatingMenu.setScaleX(0.5f);
        floatingMenu.setScaleY(0.5f);
        floatingMenu.setAlpha(0f);
        floatingMenu.animate()
                .scaleX(1f)
                .scaleY(1f)
                .alpha(1f)
                .setDuration(300)
                .setInterpolator(new OvershootInterpolator(1.2f))
                .start();
    }

    private void hideMenu() {
        if (!isMenuVisible) return;

        floatingMenu.animate()
                .scaleX(0.5f)
                .scaleY(0.5f)
                .alpha(0f)
                .setDuration(200)
                .setInterpolator(new AccelerateDecelerateInterpolator())
                .setListener(new AnimatorListenerAdapter() {
                    @Override
                    public void onAnimationEnd(Animator animation) {
                        try {
                            windowManager.removeView(floatingMenu);
                        } catch (Exception ignored) {}
                        isMenuVisible = false;
                        floatingMenu.animate().setListener(null);
                    }
                })
                .start();
    }

    private void setupStatusListener() {
        ScriptManager.setStatusListener(status ->
                handler.post(() -> updateStatus(status,
                        !status.contains("failed") && !status.contains("error"))));
    }

    private void updateStatus(String message, boolean success) {
        handler.post(() -> {
            tvStatus.setText(message);
            if (success) {
                tvStatus.setTextColor(Color.parseColor("#00E676"));
                setStatusDotColor("#00E676");
            } else {
                tvStatus.setTextColor(Color.parseColor("#FF5252"));
                setStatusDotColor("#FF5252");
            }

            handler.postDelayed(() -> {
                tvStatus.setText("Ready");
                tvStatus.setTextColor(Color.parseColor("#00E676"));
                setStatusDotColor("#00E676");
            }, 3000);
        });
    }

    private void setStatusDotColor(String color) {
        GradientDrawable dot = new GradientDrawable();
        dot.setShape(GradientDrawable.OVAL);
        dot.setColor(Color.parseColor(color));
        dot.setSize(dpToPx(8), dpToPx(8));
        statusDot.setBackground(dot);
    }

    private void animateButton(View view) {
        view.animate()
                .scaleX(0.9f)
                .scaleY(0.9f)
                .setDuration(100)
                .withEndAction(() ->
                        view.animate()
                                .scaleX(1f)
                                .scaleY(1f)
                                .setDuration(100)
                                .start())
                .start();
    }

    private void startPulseAnimation() {
        ObjectAnimator scaleX = ObjectAnimator.ofFloat(floatingButton, "scaleX", 1f, 1.15f, 1f);
        ObjectAnimator scaleY = ObjectAnimator.ofFloat(floatingButton, "scaleY", 1f, 1.15f, 1f);
        scaleX.setDuration(2000);
        scaleY.setDuration(2000);
        scaleX.setRepeatCount(ValueAnimator.INFINITE);
        scaleY.setRepeatCount(ValueAnimator.INFINITE);
        scaleX.setInterpolator(new AccelerateDecelerateInterpolator());
        scaleY.setInterpolator(new AccelerateDecelerateInterpolator());
        scaleX.start();
        scaleY.start();
    }

    private int dpToPx(int dp) {
        return (int) (dp * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        try {
            if (floatingButton != null) windowManager.removeView(floatingButton);
        } catch (Exception ignored) {}
        try {
            if (isMenuVisible && floatingMenu != null) windowManager.removeView(floatingMenu);
        } catch (Exception ignored) {}
    }
}
