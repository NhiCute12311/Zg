package com.zg.luainjector;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {

    private static final int OVERLAY_PERMISSION_CODE = 1001;
    private static boolean moduleActive = false;

    public static void setModuleActive() {
        moduleActive = true;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        TextView tvStatus = findViewById(R.id.tvModuleStatus);

        if (moduleActive) {
            tvStatus.setText("Module Status: ✅ Active");
            tvStatus.setTextColor(0xFF00E676);
        } else {
            tvStatus.setText("Module Status: ❌ Not activated in LSPosed");
            tvStatus.setTextColor(0xFFFF5252);
        }

        checkOverlayPermission();
    }

    private void checkOverlayPermission() {
        if (!Settings.canDrawOverlays(this)) {
            Intent intent = new Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName())
            );
            startActivityForResult(intent, OVERLAY_PERMISSION_CODE);
            Toast.makeText(this,
                    "Please grant overlay permission for the floating menu",
                    Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == OVERLAY_PERMISSION_CODE) {
            if (Settings.canDrawOverlays(this)) {
                Toast.makeText(this, "Overlay permission granted!", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(this, "Overlay permission is required!", Toast.LENGTH_SHORT).show();
            }
        }
    }
}
