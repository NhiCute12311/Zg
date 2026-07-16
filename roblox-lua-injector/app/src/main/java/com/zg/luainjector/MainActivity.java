package com.zg.luainjector;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {

    private static final int OVERLAY_CODE = 1001;
    private static boolean moduleActive = false;

    public static void setModuleActive() { moduleActive = true; }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        int dp8 = dp(8), dp16 = dp(16), dp32 = dp(32);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(0xFF1A1A2E);
        root.setPadding(dp32, dp32, dp32, dp32);

        // Icon
        TextView icon = new TextView(this);
        icon.setText("⚡");
        icon.setTextSize(64);
        icon.setGravity(Gravity.CENTER);
        root.addView(icon);

        // Title
        TextView title = new TextView(this);
        title.setText("ZG Lua Injector");
        title.setTextColor(0xFFEAEAEA);
        title.setTextSize(28);
        title.setTypeface(null, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tLp = new LinearLayout.LayoutParams(-2, -2);
        tLp.topMargin = dp16;
        root.addView(title, tLp);

        // Subtitle
        TextView sub = new TextView(this);
        sub.setText("Roblox Script Executor");
        sub.setTextColor(0xFFA0A0B0);
        sub.setTextSize(16);
        sub.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams sLp = new LinearLayout.LayoutParams(-2, -2);
        sLp.topMargin = dp8;
        root.addView(sub, sLp);

        // Divider
        View divider = new View(this);
        GradientDrawable divBg = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{0xFF6C63FF, 0xFF9D4EDD});
        divBg.setCornerRadius(dp(2));
        divider.setBackground(divBg);
        LinearLayout.LayoutParams dLp = new LinearLayout.LayoutParams(dp(60), dp(3));
        dLp.topMargin = dp(24);
        dLp.gravity = Gravity.CENTER;
        root.addView(divider, dLp);

        // Status
        TextView status = new TextView(this);
        if (moduleActive) {
            status.setText("Module Status: Active");
            status.setTextColor(0xFF00E676);
        } else {
            status.setText("Module Status: Not activated in LSPosed");
            status.setTextColor(0xFFFF5252);
        }
        status.setTextSize(14);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams stLp = new LinearLayout.LayoutParams(-2, -2);
        stLp.topMargin = dp32;
        root.addView(status, stLp);

        // Info
        TextView info = new TextView(this);
        info.setText("Open Roblox to see the floating menu.\nThe inject button will appear as an overlay.");
        info.setTextColor(0xFFA0A0B0);
        info.setTextSize(13);
        info.setGravity(Gravity.CENTER);
        info.setLineSpacing(0, 1.4f);
        LinearLayout.LayoutParams iLp = new LinearLayout.LayoutParams(-2, -2);
        iLp.topMargin = dp(24);
        root.addView(info, iLp);

        // Version
        TextView ver = new TextView(this);
        ver.setText("v1.0.0 | LSPosed Module");
        ver.setTextColor(0xFF505060);
        ver.setTextSize(11);
        ver.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams vLp = new LinearLayout.LayoutParams(-2, -2);
        vLp.topMargin = dp(48);
        root.addView(ver, vLp);

        setContentView(root);
        checkOverlayPermission();
    }

    private void checkOverlayPermission() {
        if (!Settings.canDrawOverlays(this)) {
            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
            startActivityForResult(intent, OVERLAY_CODE);
            Toast.makeText(this, "Please grant overlay permission", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == OVERLAY_CODE) {
            if (Settings.canDrawOverlays(this))
                Toast.makeText(this, "Overlay permission granted!", Toast.LENGTH_SHORT).show();
            else
                Toast.makeText(this, "Overlay permission required!", Toast.LENGTH_SHORT).show();
        }
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density);
    }
}
