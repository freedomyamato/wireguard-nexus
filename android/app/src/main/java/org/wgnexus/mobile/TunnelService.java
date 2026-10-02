package org.wgnexus.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import com.wireguard.android.backend.Tunnel;

/** Visible, user-started session supervisor. OS always-on/lockdown is not claimed. */
public final class TunnelService extends Service {
    private NexusApp app;
    @Override public void onCreate() {
        super.onCreate(); app=(NexusApp)getApplication();
        getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("vpn", "VPN session", NotificationManager.IMPORTANCE_LOW));
    }
    @Override public int onStartCommand(Intent intent, int flags, int id) {
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,TunnelService.class).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE);
        startForeground(1,new Notification.Builder(this,"vpn").setContentTitle("WireGuard Nexus")
            .setContentText("VPN session running. Open Nexus for tunnel status.")
            .setSmallIcon(android.R.drawable.ic_lock_lock).setContentIntent(open).setOngoing(true)
            .addAction(new Notification.Action.Builder(null,"Disconnect",stop).build()).build());
        boolean stopping=intent!=null && "STOP".equals(intent.getAction());
        if (app.busy && !stopping) return START_NOT_STICKY;
        app.busy=true;
        app.worker.execute(()->{
            try {
                if(stopping) {
                    app.backend().setState(app.tunnel,Tunnel.State.DOWN,null);stopSelf();
                } else {
                    String profile=new ProfileStore(this).load();
                    if(profile==null)throw new IllegalStateException();
                    app.backend().setState(app.tunnel,Tunnel.State.UP,NexusApp.parse(profile));
                }
            } catch(Exception|LinkageError error) { app.message="Session failed; check profile and Android VPN settings."; stopSelf(); }
            finally { app.busy=false; }
        });
        // No unattended reconnection after force-stop, permission revocation or process death.
        return START_NOT_STICKY;
    }
    @Override public void onDestroy() {
        app.worker.execute(()->{
            try { if(app.backend!=null)app.backend.setState(app.tunnel,Tunnel.State.DOWN,null); }
            catch(Exception ignored) { }
        });
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
