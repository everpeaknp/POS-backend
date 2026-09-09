from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import SupportTicket, SupportTicketMessage


class SupportTicketAdminForm(forms.ModelForm):
    # Deliberately excluded from every fieldset below — the actual <textarea
    # name="reply_body"> / <input name="reply_attachment"> are hand-written
    # as part of conversation_view()'s HTML, styled as a chat composer bar
    # pinned under the thread. Declared here only so Django still binds and
    # validates them by name when the form (the whole change page) submits.
    reply_body = forms.CharField(required=False)
    reply_attachment = forms.FileField(required=False)

    class Meta:
        model = SupportTicket
        fields = '__all__'


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    form = SupportTicketAdminForm
    list_display = ['id', 'subject', 'tenant', 'user', 'category', 'priority', 'status', 'message_count', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['subject', 'message', 'tenant__name', 'user__email', 'user__username']
    readonly_fields = [
        'tenant', 'user', 'subject', 'category', 'priority', 'message',
        'conversation_view', 'created_at', 'updated_at',
    ]

    fieldsets = (
        ('Ticket', {
            'fields': ('tenant', 'user', 'subject', 'category', 'priority', 'message'),
        }),
        ('Status', {
            'fields': ('status', 'resolved_at'),
        }),
        ('Conversation', {
            'fields': ('conversation_view',),
            'description': 'Same chat shown to the user on /dashboard/settings/help — reply below, it posts on Save.',
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        # SupportTicket is tenant-scoped (TenantManager returns .none() with
        # no tenant set on the thread, which admin requests never set).
        return SupportTicket._base_manager.all()

    @admin.display(description='Messages')
    def message_count(self, obj):
        count = obj.messages.filter(message_type=SupportTicketMessage.TYPE_MESSAGE).count()
        return format_html('{}', count)

    def get_urls(self):
        urls = [
            path(
                '<int:pk>/thread-fragment/',
                self.admin_site.admin_view(self.thread_fragment_view),
                name='helpdesk_supportticket_thread_fragment',
            ),
        ]
        return urls + super().get_urls()

    def thread_fragment_view(self, request, pk):
        obj = SupportTicket._base_manager.filter(pk=pk).first()
        if not obj:
            return JsonResponse({'error': 'not found'}, status=404)
        thread_html, timeline_html, last_id = self._build_thread_and_timeline(obj)
        return JsonResponse({
            'thread_html': thread_html,
            'timeline_html': timeline_html,
            'last_id': last_id,
            'status_display': obj.get_status_display(),
        })

    def _build_thread_and_timeline(self, obj):
        messages = list(obj.messages.select_related('author').order_by('created_at'))
        last_id = messages[-1].id if messages else 0
        status_events = [
            (m.body or f'Status changed to {m.new_status}', m.created_at)
            for m in messages
            if m.message_type == SupportTicketMessage.TYPE_STATUS_CHANGE
        ]
        timeline_rows = [('Ticket opened', obj.created_at)] + status_events

        bubbles = []
        for m in messages:
            if m.message_type != SupportTicketMessage.TYPE_MESSAGE:
                bubbles.append(format_html(
                    '<div style="text-align:center;margin:10px 0;">'
                    '<span style="font-size:11px;color:#6b7280;background:#f3f4f6;padding:4px 12px;'
                    'border-radius:9999px;">{} · {}</span></div>',
                    m.body or f'Status changed to {m.new_status}',
                    timezone.localtime(m.created_at).strftime('%b %d, %Y %I:%M %p'),
                ))
                continue

            # From the admin's own perspective (this page), staff replies —
            # i.e. what "I" (the logged-in admin) sent — go right/green,
            # mirroring the frontend where the ticket owner sees *their*
            # own messages on the right. The customer's messages go left/gray.
            is_staff = m.is_staff
            author = 'You' if is_staff else (m.author.get_full_name() if m.author else 'User')

            attachment_html = ''
            if m.attachment:
                fname = m.attachment.name.rsplit('/', 1)[-1]
                attachment_html = format_html(
                    '<div style="margin-top:6px;"><a href="{}" target="_blank" '
                    'style="font-size:12px;text-decoration:underline;color:inherit;">\U0001F4CE {}</a></div>',
                    m.attachment.url, fname,
                )

            bubbles.append(format_html(
                '<div style="display:flex;justify-content:{};margin:6px 0;">'
                '<div style="max-width:70%;">'
                '<div style="background:{};color:{};padding:10px 14px;'
                'border-radius:{};font-size:13px;white-space:pre-wrap;word-break:break-word;">{}{}</div>'
                '<div style="font-size:11px;color:#9ca3af;margin-top:3px;text-align:{};">{} · {}</div>'
                '</div></div>',
                'flex-end' if is_staff else 'flex-start',
                '#22C55E' if is_staff else '#f3f4f6',
                '#fff' if is_staff else '#111827',
                '18px 18px 4px 18px' if is_staff else '18px 18px 18px 4px',
                m.body, attachment_html,
                'right' if is_staff else 'left',
                author, timezone.localtime(m.created_at).strftime('%I:%M %p'),
            ))

        thread_html = mark_safe(''.join(bubbles)) if bubbles else format_html(
            '<div style="color:#9ca3af;font-size:13px;">No messages yet.</div>'
        )

        timeline_html = format_html_join(
            '',
            '<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #f3f4f6;">'
            '<span style="color:#9ca3af;">●</span>'
            '<div><div style="font-size:12px;color:#111827;">{}</div>'
            '<div style="font-size:11px;color:#9ca3af;">{}</div></div></div>',
            ((label, timezone.localtime(ts).strftime('%b %d, %Y %I:%M %p')) for label, ts in timeline_rows),
        )

        return thread_html, timeline_html, last_id

    @admin.display(description='')
    def conversation_view(self, obj):
        if not obj or not obj.pk:
            return format_html('<span style="color:#9ca3af;">Save the ticket first to see the conversation.</span>')

        thread_html, timeline_html, last_id = self._build_thread_and_timeline(obj)
        fragment_url = f'/admin/helpdesk/supportticket/{obj.pk}/thread-fragment/'
        status_label = obj.get_status_display()
        composer = format_html(
            '<div style="border-top:1px solid #e5e7eb;padding:12px;background:#fff;">'
            '<div id="admin-reply-preview" style="display:none;align-items:center;gap:8px;'
            'margin-bottom:8px;padding:8px 10px;border:1px solid #e5e7eb;border-radius:8px;background:#f9fafb;">'
            '<span style="font-size:12px;color:#374151;flex:1;" id="admin-reply-preview-name"></span>'
            '<span onclick="'
            'document.getElementById(\'id_reply_attachment\').value=\'\';'
            'document.getElementById(\'admin-reply-preview\').style.display=\'none\';'
            '" style="cursor:pointer;color:#9ca3af;font-size:14px;">✕</span>'
            '</div>'
            '<div style="display:flex;align-items:flex-end;gap:8px;">'
            '<label for="id_reply_attachment" title="Attach a file (image or PDF)" style="cursor:pointer;'
            'width:38px;height:38px;border:1px solid #d1d5db;background:#f9fafb;border-radius:10px;'
            'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" '
            'stroke="#4b5563" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
            '</svg></label>'
            '<input type="file" name="reply_attachment" id="id_reply_attachment" style="display:none;" '
            'accept="image/png,image/jpeg,image/gif,image/webp,.pdf" onchange="'
            'const f=this.files[0];'
            'const p=document.getElementById(\'admin-reply-preview\');'
            'const n=document.getElementById(\'admin-reply-preview-name\');'
            'if(f){{n.textContent=f.name+\' (\'+Math.round(f.size/1024)+\' KB)\';p.style.display=\'flex\';}}'
            'else{{p.style.display=\'none\';}}'
            '">'
            '<textarea name="reply_body" id="id_reply_body" rows="1" placeholder="Type a message..." '
            'style="flex:1;resize:none;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;'
            'font-size:13px;font-family:inherit;max-height:120px;" '
            'oninput="this.style.height=\'auto\';this.style.height=this.scrollHeight+\'px\';" '
            'onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){{event.preventDefault();'
            'this.form.querySelector(\'[name=_continue]\').click();}}"></textarea>'
            '<button type="submit" name="_continue" title="Send" style="flex-shrink:0;width:38px;height:38px;'
            'border-radius:10px;background:#22C55E;color:#fff;border:none;cursor:pointer;'
            'display:flex;align-items:center;justify-content:center;">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" '
            'stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>'
            '</svg></button>'
            '</div>'
            '<p style="font-size:11px;color:#9ca3af;margin:6px 2px 0;">'
            'Sends as a message in this ticket\'s thread · status shown to user: {}'
            '</p>'
            '</div>',
            status_label,
        )

        style = mark_safe(
            '<style>'
            # Only the field's OWN label (a direct child of the field
            # wrapper) should be hidden — a descendant selector here would
            # also catch the composer's <label for="id_reply_attachment">
            # (the attach button) nested inside this field's content.
            '.field-conversation_view > label, label[for="id_conversation_view"] { display:none !important; }'
            '.field-conversation_view, .form-group.field-conversation_view, .form-row.field-conversation_view,'
            '.field-box.field-conversation_view {'
            '  width:100% !important; max-width:none !important; float:none !important; padding-left:0 !important;'
            '  clear:both !important;'
            '}'
            '.field-conversation_view .readonly { width:100% !important; max-width:none !important; }'
            '</style>'
        )

        return format_html(
            '{}'
            '<div id="helpdesk-conversation-root" data-last-id="{}" data-fragment-url="{}" '
            'style="display:flex;gap:16px;align-items:stretch;width:100%;height:calc(100vh - 300px);min-height:520px;">'
            '<div style="flex:1;min-width:0;background:#fff;border:1px solid #e5e7eb;border-radius:12px;'
            'overflow:hidden;display:flex;flex-direction:column;">'
            '<div id="helpdesk-thread-scroll" style="flex:1;min-height:0;overflow-y:auto;padding:16px;">{}</div>{}</div>'
            '<div style="width:280px;flex-shrink:0;background:#fff;border:1px solid #e5e7eb;'
            'border-radius:12px;padding:14px;overflow-y:auto;">'
            '<div style="font-size:12px;font-weight:600;color:#111827;margin-bottom:8px;">Timeline</div>'
            '<div id="helpdesk-timeline">{}</div></div>'
            '</div>'
            '<script>'
            '(function(){{'
            'var root=document.getElementById("helpdesk-conversation-root");'
            'var threadEl=document.getElementById("helpdesk-thread-scroll");'
            'var timelineEl=document.getElementById("helpdesk-timeline");'
            'if(!root)return;'
            'function scrollToBottom(){{threadEl.scrollTop=threadEl.scrollHeight;}}'
            'scrollToBottom();'
            'setTimeout(scrollToBottom,150);'
            # Jazzmin tabs are just display:none toggles — content (and this
            # script) already exists in the DOM on page load even if the
            # Conversation tab isn't the active one yet, and scrollHeight is
            # unreliable on a hidden element. Re-scroll once the tab is shown.
            'var tabLinks=document.querySelectorAll(\'a[href="#conversation-tab"], a[href="#conversation"]\');'
            'tabLinks.forEach(function(a){{a.addEventListener("click",function(){{setTimeout(scrollToBottom,50);}});}});'
            'function poll(){{'
            'fetch(root.dataset.fragmentUrl,{{credentials:"same-origin"}})'
            '.then(function(r){{return r.json();}})'
            '.then(function(data){{'
            'var currentId=root.dataset.lastId;'
            'if(String(data.last_id)!==currentId){{'
            'threadEl.innerHTML=data.thread_html;'
            'timelineEl.innerHTML=data.timeline_html;'
            'root.dataset.lastId=data.last_id;'
            'scrollToBottom();'
            '}}'
            '}}).catch(function(){{}});'
            '}}'
            'if(window.__helpdeskPollTimer)clearInterval(window.__helpdeskPollTimer);'
            'window.__helpdeskPollTimer=setInterval(poll,4000);'
            '}})();'
            '</script>',
            style, last_id, fragment_url, thread_html, composer, timeline_html,
        )

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        # A composer send posts a reply_body/reply_attachment — land the
        # admin back on the Conversation tab instead of it resetting to the
        # first tab (Jazzmin picks the active tab from the URL fragment,
        # which a plain redirect Location doesn't carry).
        sent_reply = bool((request.POST.get('reply_body') or '').strip() or request.FILES.get('reply_attachment'))
        if sent_reply and isinstance(response, HttpResponseRedirect):
            response['Location'] = f'{response["Location"]}#conversation-tab'
        return response

    def save_model(self, request, obj, form, change):
        old_status = None
        if change:
            old_status = SupportTicket._base_manager.get(pk=obj.pk).status

        if change and 'status' in form.changed_data and obj.status in ('resolved', 'closed'):
            obj.resolved_at = timezone.now()

        super().save_model(request, obj, form, change)

        if change and old_status and old_status != obj.status:
            SupportTicketMessage.objects.create(
                ticket=obj,
                author=request.user,
                is_staff=True,
                message_type=SupportTicketMessage.TYPE_STATUS_CHANGE,
                old_status=old_status,
                new_status=obj.status,
                body=f'Status changed from {old_status} to {obj.status}.',
            )

        reply_body = (form.cleaned_data.get('reply_body') or '').strip()
        reply_attachment = form.cleaned_data.get('reply_attachment')
        if reply_body or reply_attachment:
            SupportTicketMessage.objects.create(
                ticket=obj,
                author=request.user,
                is_staff=True,
                message_type=SupportTicketMessage.TYPE_MESSAGE,
                body=reply_body,
                attachment=reply_attachment,
            )
