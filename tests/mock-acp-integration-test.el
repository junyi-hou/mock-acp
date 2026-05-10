;;; mock-acp-integration-test.el --- Integration tests for mock-acp using acp.el -*- lexical-binding: t; -*-

(require 'ert)
(require 'acp)
(require 'cl-lib)

(defconst mock-acp-integration--project-root
  (locate-dominating-file (or load-file-name default-directory) "pyproject.toml")
  "Root directory of the mock-acp project.")

(defconst mock-acp-integration--python
  (expand-file-name ".venv/bin/python" mock-acp-integration--project-root)
  "Path to Python binary in the project's virtual environment.")

(defmacro mock-acp-integration--with-client (client-var &rest body)
  "Evaluate BODY with CLIENT-VAR bound to a live mock-acp client.
Ensures the subprocess runs in the project root directory and handles cleanup."
  (declare (indent 1))
  `(let ((default-directory mock-acp-integration--project-root)
         (,client-var (acp-make-client
                       :command mock-acp-integration--python
                       :command-params '("src/main.py"))))
     (unwind-protect
         (progn ,@body)
       (acp-shutdown :client ,client-var))))

(defun mock-acp-integration--initialize (client)
  (acp-send-request
   :client client
   :request (acp-make-initialize-request
             :protocol-version 1
             :read-text-file-capability t
             :write-text-file-capability t)
   :sync t))

(defun mock-acp-integration--new-session (client)
  (acp-send-request
   :client client
   :request (acp-make-session-new-request :cwd "/tmp")
   :sync t))

(defun mock-acp-integration--prompt (client session-id text)
  (acp-send-request
   :client client
   :request (acp-make-session-prompt-request
             :session-id session-id
             :prompt `(((type . "text") (text . ,text))))
   :sync t))

(defun mock-acp-integration--collect-notifications (client)
  "Subscribe to notifications on CLIENT. Returns a list whose tail is mutated
in place as notifications arrive. Use (cdr collected) for the actual items."
  (let ((collected (list :head)))
    (acp-subscribe-to-notifications
     :client client
     :on-notification (lambda (n) (nconc collected (list n))))
    collected))

(defun mock-acp-integration--collect-requests (client)
  "Subscribe to incoming requests on CLIENT. Returns a list whose tail is
mutated in place as requests arrive. Use (cdr collected) for the actual items."
  (let ((collected (list :head)))
    (acp-subscribe-to-requests
     :client client
     :on-request (lambda (r) (nconc collected (list r))))
    collected))

(defun mock-acp-integration--update (notification)
  "Extract the update object from a session/update NOTIFICATION."
  (map-nested-elt notification '(params update)))

(defun mock-acp-integration--update-type (notification)
  "Extract the sessionUpdate discriminator from a session/update NOTIFICATION."
  (map-elt (mock-acp-integration--update notification) 'sessionUpdate))

(defun mock-acp-integration--update-content (notification)
  "Extract the content block from a session/update NOTIFICATION update."
  (map-elt (mock-acp-integration--update notification) 'content))

(defun mock-acp-integration--auto-respond (client)
  "Subscribe to incoming requests on CLIENT and auto-respond to known types."
  (acp-subscribe-to-requests
   :client client
   :on-request (lambda (req)
                 (let ((method (map-elt req 'method))
                       (id (map-elt req 'id)))
                   (cond
                    ((equal method "session/request_permission")
                     (acp-send-response
                      :client client
                      :response (acp-make-session-request-permission-response
                                 :request-id id :option-id "allow_once")))
                    ((equal method "fs/read_text_file")
                     (acp-send-response
                      :client client
                      :response (acp-make-fs-read-text-file-response
                                 :request-id id :content "")))
                    ((equal method "fs/write_text_file")
                     (acp-send-response
                      :client client
                      :response (acp-make-fs-write-text-file-response
                                 :request-id id)))
                    (t (error "Unhandled incoming request: %s" method)))))))


;;; Tests

(ert-deftest mock-acp-integration-initialize ()
  "Initialize returns protocol version and capabilities."
  (mock-acp-integration--with-client client
    (let ((result (mock-acp-integration--initialize client)))
      (should result)
      (should (equal (map-elt result 'protocolVersion) 1))
      (should (map-elt result 'agentCapabilities))
      (should (map-nested-elt result '(agentCapabilities promptCapabilities))))))

(ert-deftest mock-acp-integration-session-new ()
  "Session/new returns the golden session ID."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let ((result (mock-acp-integration--new-session client)))
      (should result)
      (let ((id (map-elt result 'sessionId)))
        (should (stringp id))
        (should (string= id "sess_abc123def456"))))))

(ert-deftest mock-acp-integration-session-list ()
  "Session/list returns an empty sessions list."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let ((result (acp-send-request
                   :client client
                   :request (acp-make-session-list-request :cwd "/tmp")
                   :sync t)))
      (should result)
      (should (map-elt result 'sessions))
      (should (= (length (map-elt result 'sessions)) 0)))))

(ert-deftest mock-acp-integration-invalid-prompt ()
  "A non-test prompt returns end_turn without errors."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (result (mock-acp-integration--prompt client session-id "hello")))
      (should result)
      (should (equal (map-elt result 'stopReason) "end_turn")))))


;;; Notification tests (agent -> client session/update)

(ert-deftest mock-acp-integration-prompt-agent-message ()
  "Prompt with 'test agent_message' triggers an AgentMessageChunk with correct text."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test agent_message"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 1))
      (let* ((n (car notifications))
             (content (mock-acp-integration--update-content n)))
        (should (equal (mock-acp-integration--update-type n) "agent_message_chunk"))
        (should (equal (map-elt content 'type) "text"))
        (should (equal (map-elt content 'text) "The capital of France is Paris."))))))

(ert-deftest mock-acp-integration-prompt-agent-thought ()
  "Prompt with 'test thought' triggers an AgentThoughtChunk notification."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test thought"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 1))
      (let* ((n (car notifications))
             (content (mock-acp-integration--update-content n)))
        (should (equal (mock-acp-integration--update-type n) "agent_thought_chunk"))
        (should (equal (map-elt content 'type) "text"))
        (should (string-match "Thinking" (map-elt content 'text)))))))

(ert-deftest mock-acp-integration-prompt-plan ()
  "Prompt with 'test plan' triggers a PlanUpdate notification with two entries."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test plan"))
           (notifications (cdr collected)))
      (should result)
      ;; see `src/main.py' line 63 - 68
      (should (= (length notifications) 2))
      (let* ((first (car notifications))
             (update (mock-acp-integration--update first)))
        (should (equal (map-elt update 'sessionUpdate) "plan"))
        (let ((entries (map-elt update 'entries)))
          (should entries)
          (should (= (length entries) 2))))

      (let* ((second (cadr notifications))
             (update (mock-acp-integration--update second)))
        (should (equal (map-elt update 'sessionUpdate) "plan"))
        (let ((entries (map-elt update 'entries)))
          (should entries)
          (should (= (length entries) 2))
          (should (equal (mapcar (lambda (e) (map-elt e 'status)) entries) '("completed" "completed"))))))))

(ert-deftest mock-acp-integration-prompt-tool-call ()
  "Prompt with 'test tool_call' triggers ToolCallStart and ToolCallProgress."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test tool_call"))
           (notifications (cdr collected)))
      (should result)
      (let ((types (mapcar #'mock-acp-integration--update-type notifications))
            (status (mapcar (lambda (n) (map-nested-elt n '(params update status))) notifications)))
        (should (member "tool_call" types))
        (should (member "tool_call_update" types))
        (should (equal "pending" (car status)))
        (should (equal "in_progress" (cadr status)))
        (should (equal "completed" (caddr status))))

      (let ((start (cl-find "tool_call" notifications
                            :test #'equal :key #'mock-acp-integration--update-type)))
        (should (equal (map-elt (mock-acp-integration--update start) 'toolCallId)
                       "call_001"))))))

(ert-deftest mock-acp-integration-prompt-tool-call-locations ()
  "Prompt with 'test tool_call_locations' triggers a ToolCallStart with locations and rawInput."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test tool_call_locations"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 2))
      (let ((start (cl-find "tool_call" notifications
                            :test #'equal :key #'mock-acp-integration--update-type)))
        (should start)
        (let* ((update (mock-acp-integration--update start))
               (locations (map-elt update 'locations))
               (raw-input (map-elt update 'rawInput)))
          (should locations)
          (should (= (length locations) 1))
          (should (equal (map-elt (aref locations 0) 'path) "/home/user/project/src/config.json"))
          (should (equal (map-elt raw-input 'path) "/home/user/project/src/config.json")))))))

(ert-deftest mock-acp-integration-prompt-user-message ()
  "Prompt with 'test user_message' triggers a UserMessageChunk notification."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test user_message"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 1))
      (let* ((n (car notifications))
             (content (mock-acp-integration--update-content n)))
        (should (equal (mock-acp-integration--update-type n) "user_message_chunk"))
        (should (equal (map-elt content 'type) "text"))
        (should (equal (map-elt content 'text) "What's the capital of France?"))))))

(ert-deftest mock-acp-integration-prompt-usage ()
  "Prompt with 'test usage' triggers a UsageUpdate notification."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test usage"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 1))
      (let* ((n (car notifications))
             (update (mock-acp-integration--update n)))
        (should (equal (map-elt update 'sessionUpdate) "usage_update"))
        (should (>= (map-elt update 'used) 0))
        (should (>= (map-elt update 'size) 0))))))

(ert-deftest mock-acp-integration-prompt-config-option ()
  "Prompt with 'test config_option' triggers a ConfigOptionUpdate notification."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-notifications client))
           (result (mock-acp-integration--prompt client session-id "test config_option"))
           (notifications (cdr collected)))
      (should result)
      (should (= (length notifications) 1))
      (let* ((n (car notifications))
             (update (mock-acp-integration--update n)))
        (should (equal (map-elt update 'sessionUpdate) "config_option_update"))
        (should (map-elt update 'configOptions))))))


;;; Agent-to-client request tests

(ert-deftest mock-acp-integration-request-permission ()
  "Prompt with 'test request_permission' triggers a permission request with options."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-requests client)))
      (mock-acp-integration--auto-respond client)
      (let ((result (mock-acp-integration--prompt client session-id "test request_permission"))
            (requests (cdr collected)))
        (should result)
        (should (= (length requests) 1))
        (let* ((req (car requests))
               (params (map-elt req 'params))
               (options (map-elt params 'options)))
          (should (equal (map-elt req 'method) "session/request_permission"))
          (should (map-elt params 'sessionId))
          (should (= (length options) 2))
          (should (cl-find "allow_once" options :test #'equal :key (lambda (o) (map-elt o 'kind))))
          (should (cl-find "reject_once" options :test #'equal :key (lambda (o) (map-elt o 'kind)))))))))

(ert-deftest mock-acp-integration-request-fs-read ()
  "Prompt with 'test fs_read' triggers an fs/read_text_file request."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-requests client)))
      (mock-acp-integration--auto-respond client)
      (let ((result (mock-acp-integration--prompt client session-id "test fs_read"))
            (requests (cdr collected)))
        (should result)
        (should (= (length requests) 1))
        (let* ((req (car requests))
               (params (map-elt req 'params)))
          (should (equal (map-elt req 'method) "fs/read_text_file"))
          (should (map-elt params 'path))
          (should (map-elt params 'line))
          (should (map-elt params 'limit)))))))

(ert-deftest mock-acp-integration-request-fs-write ()
  "Prompt with 'test fs_write' triggers an fs/write_text_file request."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (collected (mock-acp-integration--collect-requests client)))
      (mock-acp-integration--auto-respond client)
      (let ((result (mock-acp-integration--prompt client session-id "test fs_write"))
            (requests (cdr collected)))
        (should result)
        (should (= (length requests) 1))
        (let* ((req (car requests))
               (params (map-elt req 'params)))
          (should (equal (map-elt req 'method) "fs/write_text_file"))
          (should (map-elt params 'path))
          (should (map-elt params 'content)))))))


(ert-deftest mock-acp-integration-prompt-all ()
  "Prompt with 'test all' triggers all notification types and agent-to-client requests."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           (notif-collected (mock-acp-integration--collect-notifications client))
           (req-collected (mock-acp-integration--collect-requests client)))
      (mock-acp-integration--auto-respond client)
      (let ((result (mock-acp-integration--prompt client session-id "test all"))
            (notifications (cdr notif-collected))
            (requests (cdr req-collected)))
        (should result)
        (should notifications)
        (should requests)
        (let ((types (mapcar #'mock-acp-integration--update-type notifications))
              (methods (mapcar (lambda (r) (map-elt r 'method)) requests)))
          (should (member "agent_message_chunk" types))
          (should (member "plan" types))
          (should (member "tool_call" types))
          (should (member "usage_update" types))
          (should (member "session/request_permission" methods))
          (should (member "fs/read_text_file" methods))
          (should (member "fs/write_text_file" methods)))))))

;;; Error handling tests

(ert-deftest mock-acp-integration-prompt-error ()
  "Prompt with 'test error' causes the agent to raise a RequestError.
The error response contains code -32603 and message \"Internal error\"."
  (mock-acp-integration--with-client client
    (mock-acp-integration--initialize client)
    (let* ((session (mock-acp-integration--new-session client))
           (session-id (map-elt session 'sessionId))
           error-msg)
      (condition-case err
          (mock-acp-integration--prompt client session-id "test error")
        (error (setq error-msg (cdr err))))
      (should error-msg)
      (let ((msg (format "%s" error-msg)))
        (should (string-match "ACP request failed" msg))
        (should (string-match "-32603" msg))
        (should (string-match "Internal error" msg))))))

(provide 'mock-acp-integration-test)
;;; mock-acp-integration-test.el ends here
