package org.wgnexus.mobile;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** AES-GCM ciphertext only; the encryption key stays in Android Keystore. */
final class ProfileStore {
    private final String ALIAS;
    private final AtomicFile file;
    ProfileStore(Context context) {
        this(context, "profile");
    }
    ProfileStore(Context context, String name) {
        ALIAS = "nexus." + name + ".v1";
        file = new AtomicFile(new File(context.getNoBackupFilesDir(), name + ".enc"));
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }
    void save(String profile) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(profile.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] packed = ByteBuffer.allocate(1 + iv.length + encrypted.length)
            .put((byte) iv.length).put(iv).put(encrypted).array();
        FileOutputStream output = null;
        try {
            output = file.startWrite();
            output.write(packed);
            file.finishWrite(output);
        } catch (Exception failure) {
            if (output != null) file.failWrite(output);
            throw failure;
        }
    }
    String load() throws Exception {
        if (!file.getBaseFile().exists()) return null;
        byte[] packed = file.readFully();
        if (packed.length < 30 || packed.length > 70000 || packed[0] != 12)
            throw new IllegalStateException("Invalid encrypted profile");
        ByteBuffer buffer = ByteBuffer.wrap(packed);
        int length = buffer.get() & 255;
        byte[] iv = new byte[length]; buffer.get(iv);
        byte[] encrypted = new byte[buffer.remaining()]; buffer.get(encrypted);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
    }
    void clear() throws Exception {
        file.delete();
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS);
    }
}
