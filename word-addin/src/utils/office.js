/**
 * Office.js helpers — read/write the current Word document.
 *
 * Office.js is loaded via CDN in index.html, so `Office` and `Word`
 * are available as globals after Office.onReady() resolves.
 */

/**
 * Read the entire document as a DOCX Blob.
 * Office.js returns the file in 64 KB slices — we reassemble them.
 */
export async function getDocumentAsBlob() {
  return new Promise((resolve, reject) => {
    Office.context.document.getFileAsync(
      Office.FileType.Compressed,
      { sliceSize: 65536 },
      (result) => {
        if (result.status !== Office.AsyncResultStatus.Succeeded) {
          reject(new Error(result.error?.message || "Failed to read document"));
          return;
        }

        const file = result.value;
        const sliceCount = file.sliceCount;
        const slices = [];
        let received = 0;

        const readSlice = (index) => {
          file.getSliceAsync(index, (sliceResult) => {
            if (sliceResult.status !== Office.AsyncResultStatus.Succeeded) {
              file.closeAsync();
              reject(new Error(sliceResult.error?.message || `Failed to read slice ${index}`));
              return;
            }

            // Slice data can be ArrayBuffer or Array<number> depending on host
            const raw = sliceResult.value.data;
            slices[index] = raw instanceof ArrayBuffer ? new Uint8Array(raw) : new Uint8Array(raw);
            received++;

            if (received === sliceCount) {
              file.closeAsync();
              const totalLength = slices.reduce((acc, s) => acc + s.length, 0);
              const combined = new Uint8Array(totalLength);
              let offset = 0;
              for (const s of slices) {
                combined.set(s, offset);
                offset += s.length;
              }
              resolve(new Blob([combined], {
                type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              }));
            } else {
              readSlice(index + 1);
            }
          });
        };

        readSlice(0);
      }
    );
  });
}

/**
 * Get plain text from the document body (for validation checks like min length).
 */
export async function getDocumentText() {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load("text");
    await context.sync();
    return body.text;
  });
}

/**
 * Replace the entire document body with OOXML content from a DOCX file.
 * Falls back to returning false if insertion fails.
 */
export async function insertDocx(base64Content) {
  try {
    await Word.run(async (context) => {
      const body = context.document.body;
      body.insertFileFromBase64(base64Content, Word.InsertLocation.replace);
      await context.sync();
    });
    return true;
  } catch (err) {
    console.error("insertDocx failed:", err);
    return false;
  }
}

/**
 * Check whether Office.js is available and ready.
 */
export function isOfficeReady() {
  return typeof Office !== "undefined" && typeof Word !== "undefined";
}
