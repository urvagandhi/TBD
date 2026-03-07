import React, { useEffect, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import tippy from 'tippy.js'
import 'tippy.js/dist/tippy.css'
import 'tippy.js/themes/light.css'

export default function LiveDocumentEditor({ documentStructure, violations }) {
    const [editorHtml, setEditorHtml] = useState('')
    const [activeViolation, setActiveViolation] = useState(null)

    // Format document structure into HTML
    useEffect(() => {
        if (!documentStructure) return
        let html = ''
        if (documentStructure.title) html += `<h1>${documentStructure.title}</h1>`
        if (documentStructure.authors && documentStructure.authors.length > 0) {
            html += `<p><strong>${documentStructure.authors.map(a => a.name).join(', ')}</strong></p>`
        }
        if (documentStructure.abstract && documentStructure.abstract.text) {
            html += `<h2>Abstract</h2><p>${documentStructure.abstract.text}</p>`
        }

        if (documentStructure.sections) {
            documentStructure.sections.forEach(sec => {
                if (sec.heading) html += `<h2>${sec.heading}</h2>`
                if (sec.paragraphs) {
                    sec.paragraphs.forEach(p => {
                        html += `<p>${p.text}</p>`
                    })
                } else if (sec.content) {
                    html += `<p>${sec.content}</p>`
                }
            })
        }

        // Simple text replacement for highlighting violations
        if (violations && violations.length > 0) {
            violations.forEach(v => {
                if (!v.text || v.text.trim() === '') return

                // Escape regex for safety
                const safeText = v.text.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')
                const regex = new RegExp(`(${safeText})`, 'gi')
                // Wrap in span with data-violation-id
                html = html.replace(regex, `<span class="violation-mark" data-violation-id="${v.id}">$1</span>`)
            })
        }
        setEditorHtml(html)
    }, [documentStructure, violations])

    const editor = useEditor({
        extensions: [
            StarterKit,
            Highlight
        ],
        content: editorHtml,
        editable: true,
    }, [editorHtml])

    // Click handler for violation marks
    useEffect(() => {
        if (!editor) return

        const handleDocClick = (e) => {
            const target = e.target.closest('.violation-mark')
            if (!target) {
                setActiveViolation(null)
                return
            }

            const id = target.getAttribute('data-violation-id')
            if (!id) return

            const violation = violations.find(v => v.id === id)
            if (violation) {
                setActiveViolation({
                    target,
                    violation
                })
            }
        }

        // Attach to the editor's DOM
        const editorEl = editor.view.dom
        editorEl.addEventListener('click', handleDocClick)

        return () => editorEl.removeEventListener('click', handleDocClick)
    }, [editor, violations])

    // Tippy setup for active violation
    useEffect(() => {
        if (!activeViolation) return

        const { target, violation } = activeViolation

        const popupContent = document.createElement('div')
        popupContent.className = 'violation-popup'
        popupContent.innerHTML = `
      <div class="v-header"><strong>Violation Detected</strong></div>
      <div class="v-rule">${violation.rule_reference || 'Formatting Rule'}</div>
      <div class="v-message">${violation.message || violation.expected || 'Incorrect format'}</div>
      <div class="v-expected">
         <span class="v-old">${violation.text}</span>
         <br/>⬇️<br/>
         <span class="v-new">${violation.expected || 'Correction'}</span>
      </div>
      <div class="v-actions">
         <button class="v-btn-fix" id="btn-apply-fix">Apply Fix</button>
         <button class="v-btn-ignore" id="btn-ignore">Ignore</button>
      </div>
    `

        const instance = tippy(target, {
            content: popupContent,
            interactive: true,
            trigger: 'manual',
            placement: 'bottom',
            theme: 'light',
            onShown: () => {
                const btnFix = popupContent.querySelector('#btn-apply-fix')
                const btnIgnore = popupContent.querySelector('#btn-ignore')

                if (btnFix) {
                    btnFix.addEventListener('click', () => {
                        let transactionApplied = false
                        // naive replacement: search whole doc and replace the text.
                        editor.state.doc.descendants((node, pos) => {
                            if (node.isText && node.text.includes(violation.text) && !transactionApplied) {
                                const start = pos + node.text.indexOf(violation.text)
                                const end = start + violation.text.length
                                editor.chain().focus().setTextSelection({ from: start, to: end }).insertContent(violation.expected || '').run()
                                transactionApplied = true
                            }
                        })

                        // If the span still remains in the DOM somehow as HTML text, let's also remove the mark wrapping if necessary.
                        // Actually insertContent just replaces whatever is matching, including marks in that selection.

                        instance.hide()
                    })
                }

                if (btnIgnore) {
                    btnIgnore.addEventListener('click', () => instance.hide())
                }
            },
            onHidden: () => {
                instance.destroy()
                setActiveViolation(null)
            }
        })

        instance.show()

        return () => {
            // Cleanup if unmounted before hiding
            if (instance) instance.destroy()
        }
    }, [activeViolation, editor])

    return (
        <div className="live-editor-container">
            <EditorContent editor={editor} className="tiptap-editor" />
        </div>
    )
}
