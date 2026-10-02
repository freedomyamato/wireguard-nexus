package org.wgnexus.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.VpnService;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.EditText;
import android.text.InputType;
import com.wireguard.android.backend.Tunnel;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class MainActivity extends Activity {
    private static final int IMPORT = 10, CONSENT = 11;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private NexusApp app;
    private ProfileStore store;
    private TextView status;
    private Button connect, importProfile, forget, enroll, finishEnrollment;
    private boolean visible;
    private final Runnable poll = new Runnable() {
        public void run() { refresh(); if (visible) handler.postDelayed(this, 1500); }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        app = (NexusApp) getApplication(); store = new ProfileStore(this);
        if (!getPreferences(MODE_PRIVATE).getBoolean("noticeAccepted", false)) {
            new AlertDialog.Builder(this).setTitle("Before using Nexus")
                .setMessage("Nexus routes internet traffic through the server in your profile. "
                    + "The server operator can see connection metadata and unencrypted traffic. "
                    + "Enrollment sends your device name and public key to your Nexus server, "
                    + "which stores these with enrollment and revocation times. "
                    + "This beta stores your VPN keys encrypted on this phone and has "
                    + "no analytics or advertising SDK. It does not guarantee a kill switch "
                    + "or background reconnection. Choose a server operator you trust.")
                .setCancelable(false).setNegativeButton("Exit", (d,w) -> finish())
                .setPositiveButton("Continue", (d,w) -> {
                    getPreferences(MODE_PRIVATE).edit().putBoolean("noticeAccepted", true).apply();
                    showScreen();
                }).show();
        } else showScreen();
    }
    private void showScreen() {
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this); title.setText("WireGuard Nexus"); title.setTextSize(28);
        layout.addView(title);
        TextView note = new TextView(this);
        note.setText("Private test build · bring your own VPN server\n"); layout.addView(note);
        status = new TextView(this); status.setTextSize(18); layout.addView(status);
        enroll = button(layout, "Enroll this phone", this::enrollDialog);
        finishEnrollment = button(layout, "Finish pending enrollment", () -> finishEnrollment());
        importProfile = button(layout, "Import profile", () -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*")
                .addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(intent, IMPORT);
        });
        connect = button(layout, "Connect / Disconnect", () -> {
            if (isUp()) disconnect();
            else {
                Intent consent = VpnService.prepare(this);
                if (consent == null) connect(); else startActivityForResult(consent, CONSENT);
            }
        });
        forget = button(layout, "Forget profile", () -> new AlertDialog.Builder(this)
            .setMessage("Delete the local profile? Revoke this device on the server separately.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Delete", (d,w) -> work(() -> {
                if (isUp()) throw new IllegalStateException();
                store.clear(); new ProfileStore(this,"enrollment").clear(); app.message = "Local profile deleted.";
            }, "Could not delete profile.")).show());
        TextView limitation = new TextView(this);
        limitation.setText("\nAn active tunnel does not prove internet access. Verify your public IP "
            + "and DNS after connecting. Disconnect before replacing or deleting the profile.");
        layout.addView(limitation); setContentView(layout); refresh();
    }
    private Button button(LinearLayout layout, String label, Runnable action) {
        Button button = new Button(this); button.setText(label);
        button.setOnClickListener(v -> action.run()); layout.addView(button); return button;
    }
    private boolean isUp() {
        return app.backend != null && app.backend.getState(app.tunnel) == Tunnel.State.UP;
    }
    private interface Operation { void run() throws Exception; }
    private void work(Operation operation, String failure) {
        if (app.busy) return;
        app.busy = true; refresh();
        app.worker.execute(() -> {
            try { operation.run(); }
            catch (Exception | LinkageError error) { app.message = failure; }
            finally { app.busy = false; handler.post(this::refresh); }
        });
    }
    private void connect() {
        try {
            if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                !=android.content.pm.PackageManager.PERMISSION_GRANTED)
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},12);
            startForegroundService(new Intent(this,TunnelService.class));
        } catch(Exception error) { app.message="Could not start VPN session."; refresh(); }
    }
    private void disconnect() {
        startService(new Intent(this,TunnelService.class).setAction("STOP"));
    }
    private void enrollDialog() {
        LinearLayout fields=new LinearLayout(this); fields.setOrientation(LinearLayout.VERTICAL);
        EditText server=new EditText(this);server.setHint("https://vpn.example.com");server.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        EditText token=new EditText(this);token.setHint("Invitation token");token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText name=new EditText(this);name.setHint("Device name");name.setText("My Android");
        fields.addView(server);fields.addView(token);fields.addView(name);
        new AlertDialog.Builder(this).setTitle("Enroll with your server").setView(fields)
            .setNegativeButton("Cancel",null).setPositiveButton("Enroll",(d,w)->{
                String serverValue=server.getText().toString(), tokenValue=token.getText().toString().trim(), nameValue=name.getText().toString().trim();
                work(()->{
                if(isUp() || store.load()!=null)throw new IllegalStateException();
                EnrollmentClient client=new EnrollmentClient(this);
                client.begin(serverValue,tokenValue,nameValue);
                app.message=client.finish()?"Enrolled. Ready to connect.":"Server update pending. Tap Finish pending enrollment.";
            },"Enrollment failed. Check server URL/token; finish a pending attempt or forget it before retrying.");
            }).show();
    }
    private void finishEnrollment() {
        work(()->{
            if(isUp())throw new IllegalStateException();
            app.message=new EnrollmentClient(this).finish()?"Enrolled. Ready to connect.":"Server update pending. Try again shortly.";
        },"Could not finish enrollment. Check server availability or invitation expiry.");
    }
    @Override public void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK) { app.message = "Operation cancelled."; refresh(); return; }
        if (request == CONSENT) connect();
        if (request == IMPORT && data != null && data.getData() != null) {
            android.net.Uri uri = data.getData();
            work(() -> {
                if (isUp()) throw new IllegalStateException();
                try (InputStream input = getContentResolver().openInputStream(uri)) {
                    if (input == null) throw new IllegalStateException();
                    ByteArrayOutputStream output = new ByteArrayOutputStream();
                    byte[] chunk = new byte[4096]; int count;
                    while ((count = input.read(chunk)) != -1) {
                        if (output.size() + count > 65536) throw new IllegalArgumentException();
                        output.write(chunk, 0, count);
                    }
                    String profile = output.toString(StandardCharsets.UTF_8.name());
                    NexusApp.parse(profile); store.save(profile);new ProfileStore(this,"enrollment").clear();
                    app.message = "Profile imported. Ready to connect.";
                }
            }, "Import failed. Use a valid single-peer profile with DNS and both default routes.");
        }
    }
    private void refresh() {
        if (status == null || isDestroyed()) return;
        boolean up = isUp();
        String text = app.busy ? "Working…" : app.message;
        if (up && !app.busy) {
            try {
                var stats = app.backend.getStatistics(app.tunnel);
                text += "\nReceived: " + stats.totalRx() + " bytes\nSent: " + stats.totalTx() + " bytes";
            } catch (Exception ignored) { text += "\nTraffic counters unavailable."; }
        }
        status.setText(text); connect.setText(up ? "Disconnect" : "Connect");
        connect.setEnabled(!app.busy); importProfile.setEnabled(!app.busy && !up);
        forget.setEnabled(!app.busy && !up);
        enroll.setEnabled(!app.busy && !up);finishEnrollment.setEnabled(!app.busy && !up);
    }
    @Override protected void onResume() { super.onResume(); visible = true; handler.post(poll); }
    @Override protected void onPause() { visible = false; handler.removeCallbacks(poll); super.onPause(); }
}
