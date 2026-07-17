/**
 * Quick Sign — Drive upload endpoint.
 *
 * Deploy steps:
 *   1. Sign in as arecblackhills@gmail.com.
 *   2. Go to script.new
 *   3. Paste this whole file in, replacing the default code.
 *   4. Deploy -> New deployment -> type "Web app".
 *        Execute as: Me
 *        Who has access: Anyone
 *   5. Click Deploy, then Authorize when prompted.
 *   6. Copy the resulting /exec URL.
 *   7. Paste it into DRIVE_ENDPOINT near the top of pages/quick-sign.html.
 */

var TOKEN = 'qs-arec-2026';
var FOLDER_NAME = 'Quick Sign Submissions';

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.token !== TOKEN) {
      return jsonOut({ ok: false, error: 'Invalid token' });
    }

    var bytes = Utilities.base64Decode(data.pdf);
    var blob = Utilities.newBlob(bytes, 'application/pdf');

    var folder = getOrCreateFolder(FOLDER_NAME);
    var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH.mm');
    var name = stamp + ' — ' + data.docTitle + '.pdf';
    blob.setName(name);

    var file = folder.createFile(blob);

    try {
      MailApp.sendEmail({
        to: 'arecblackhills@gmail.com',
        subject: 'Signed document: ' + data.docTitle,
        body: 'A completed form was submitted via Quick Sign.\n\nSaved to Drive: ' + file.getUrl(),
        attachments: [blob]
      });
    } catch (mailErr) {
      // Drive save already succeeded; don't fail the submission over email.
    }

    return jsonOut({ ok: true, url: file.getUrl() });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
  }
}

function getOrCreateFolder(name) {
  var folders = DriveApp.getFoldersByName(name);
  if (folders.hasNext()) return folders.next();
  return DriveApp.createFolder(name);
}

function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
