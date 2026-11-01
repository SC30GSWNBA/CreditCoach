"""The look of the signed-in pages, matching the welcome page (``creditcoach.app.welcome``).

One stylesheet for the chat UI, loaded before ``charts.CSS`` and ``badges.CSS`` (``creditcoach.app.main``). It changes
appearance only, nothing about what the page does:

    Log out    A white button with dark words on both themes.
    Tabs       "Ask CreditCoach" and "My credit" are a two-button switch; the one you are on is solid indigo.
    Sections   Headings are larger and bold with an indigo underline; collapsible panels are outlined cards.
    Choices    Every radio option is an outlined box with a visible circle; the picked one turns indigo.
    Inputs     Text boxes and dropdowns have a clear outline, and an indigo glow while in use.
    Charts     Axis numbers, axis titles, legends and labels use the page's text color, so they read in dark mode too.
    Chat       A line inviting people to pick a question sits above the example questions, which are outlined
               buttons; the conversation has a border, and the intro text is slightly larger. Text inside chat answers
               is left as it is.
    My credit  The snapshot tiles, card bars, account list and legend (``charts.CSS``) get larger, darker labels.
               Each rule here starts with ``.gradio-container`` so it wins over the chart's own, smaller size.
"""

INK, LINE, ACCENT = "#0f172a", "#94a3b8", "#4f46e5"

CSS = """
.gradio-container {--checkbox-border-color: #475569; --checkbox-border-width: 2px;
           --checkbox-border-color-hover: #4f46e5; --checkbox-border-color-focus: #4f46e5;
           --checkbox-background-color: #ffffff; --checkbox-background-color-selected: #4f46e5;
           --checkbox-border-color-selected: #4f46e5;}

/* Tabs: a two-button switch */
.gradio-container .tab-container, .gradio-container .tab-wrapper {height: auto !important; overflow: visible !important;}
.gradio-container .tab-container {gap: 10px !important; padding: 6px !important; background: #e2e8f0;
           border-radius: 14px; display: flex !important; width: 100%;}
.gradio-container .tab-container.visually-hidden {display: none !important;}
.gradio-container .tab-container::after {display: none !important;}
.gradio-container button[role="tab"] {flex: 1 1 0; font-size: 1.15rem !important; font-weight: 700 !important;
           padding: 12px 18px !important; height: auto !important; border-radius: 10px !important;
           border: 1.5px solid transparent !important; color: #475569 !important; background: transparent !important;
           justify-content: center; text-align: center;}
.gradio-container button[role="tab"]:hover {color: #4f46e5 !important; border-color: #4f46e5 !important;}
.gradio-container button[role="tab"].selected, .gradio-container button[role="tab"][aria-selected="true"] {
           background: #4f46e5 !important; color: #ffffff !important; border-color: #4f46e5 !important;
           box-shadow: 0 2px 8px rgba(79, 70, 229, .35);}
.gradio-container button[role="tab"]::after {display: none !important;}

/* Who is signed in, and Log out */
.cc-who p {font-size: 1.1rem !important;}
.cc-logout {border: 1.5px solid #64748b !important; font-weight: 700 !important; font-size: .98rem !important;
           padding: 8px 18px !important; border-radius: 10px !important; background: #ffffff !important;
           color: #0f172a !important;}
.cc-logout:hover {border-color: #4f46e5 !important; color: #4f46e5 !important;}

/* Text outside the conversation: slightly larger; section headings bold with an underline */
.gradio-container .prose:not(.bubble-wrap .prose) p, .gradio-container .prose:not(.bubble-wrap .prose) li {
           font-size: 1.07rem; line-height: 1.55;}
.gradio-container .prose:not(.bubble-wrap .prose) h1 {font-size: 2rem; font-weight: 800; margin-bottom: .2em;}
.gradio-container .prose:not(.bubble-wrap .prose) h3 {font-size: 1.35rem !important; font-weight: 700 !important;
           padding-bottom: 6px; margin: .3em 0 .5em; border-bottom: 2px solid #4f46e5;}

/* Collapsible panels: outlined cards with a bold label */
.gradio-container .gr-accordion {border: 1.5px solid #cbd5e1 !important; border-radius: 12px !important;}
.gradio-container .gr-accordion > button.label-wrap > span:first-child {font-size: 1.12rem !important;
           font-weight: 700 !important; color: var(--body-text-color) !important;}

/* Choices: every option an outlined box with a visible circle */
.gradio-container fieldset label {border: 1.5px solid #94a3b8 !important; border-radius: 10px !important;
           padding: 9px 14px !important; background: #ffffff !important; cursor: pointer;}
.gradio-container fieldset label, .gradio-container fieldset label span {color: #0f172a !important; font-size: .98rem;}
.gradio-container fieldset label:hover {border-color: #4f46e5 !important;}
.gradio-container fieldset label.selected, .gradio-container fieldset label:has(input:checked) {
           border-color: #4f46e5 !important; background: #e0e7ff !important; box-shadow: 0 0 0 1px #4f46e5 inset;}
.gradio-container fieldset label.selected span, .gradio-container fieldset label:has(input:checked) span {
           color: #1e1b4b !important; font-weight: 700;}
.gradio-container input[type=radio], .gradio-container input[type=checkbox] {width: 20px !important;
           height: 20px !important; min-width: 20px; border: 2px solid #475569 !important; background-color: #fff;
           margin-right: 4px;}
.gradio-container input[type=radio]:checked, .gradio-container input[type=checkbox]:checked {
           border-color: #4f46e5 !important; background-color: #4f46e5 !important;}
.gradio-container [data-testid="block-info"] {font-weight: 700; font-size: 1rem;}

/* Inputs: a clear outline, and a glow while in use */
.gradio-container input[type=text], .gradio-container input[type=number], .gradio-container textarea,
.gradio-container .wrap-inner {border: 1.5px solid #64748b !important; border-radius: 8px !important;
           background: #ffffff !important; color: #0f172a !important; box-shadow: none !important;}
.gradio-container .wrap-inner input[type=text], .gradio-container .wrap-inner input {border: none !important;
           background: transparent !important;}
.gradio-container input[type=text]:focus, .gradio-container input[type=number]:focus,
.gradio-container textarea:focus, .gradio-container .wrap-inner:focus-within {border-color: #4f46e5 !important;
           box-shadow: 0 0 0 3px rgba(79, 70, 229, .25) !important; outline: none !important;}
.gradio-container textarea[data-testid="textbox"] {padding: 10px 12px !important; font-size: 1.05rem;}
.gradio-container input::placeholder, .gradio-container textarea::placeholder {color: #94a3b8 !important;}

/* Chat: a bordered conversation, and example questions that look like buttons */
.gradio-container .block:has(> .wrapper > .bubble-wrap) {border: 1.5px solid #cbd5e1 !important;
           border-radius: 12px !important;}
.gradio-container button.example {border: 1.5px solid #94a3b8 !important; border-radius: 12px !important;
           background: #ffffff !important; padding: 14px 16px !important; box-shadow: 0 1px 3px rgba(15, 23, 42, .08);}
.gradio-container button.example .example-text {font-size: 1.02rem !important; font-weight: 600 !important;
           color: #0f172a !important;}
.gradio-container button.example:hover {border-color: #4f46e5 !important; background: #eef2ff !important;}
.gradio-container .placeholder-content {justify-content: center;}
.gradio-container .placeholder-content .placeholder {flex-grow: 0 !important; height: auto !important; margin: 0;}
.gradio-container .placeholder-content .placeholder p {font-size: 1.25rem !important; text-align: center;
           color: var(--body-text-color) !important; margin: 0;}
.gradio-container .placeholder-content .examples {margin: 0 auto !important; padding-top: 16px !important;}

/* Charts: axis numbers, axis titles, legend and labels in the page's text color (not Plotly's mid grey), so they
   read on both themes. Hover boxes are left alone. */
.gradio-container .js-plotly-plot .xtick text, .gradio-container .js-plotly-plot .ytick text,
.gradio-container .js-plotly-plot .g-xtitle text, .gradio-container .js-plotly-plot .g-ytitle text,
.gradio-container .js-plotly-plot .annotation-text, .gradio-container .js-plotly-plot .textpoint text,
.gradio-container .js-plotly-plot .legendtext, .gradio-container .js-plotly-plot .legendtitletext {
           fill: var(--body-text-color) !important;}
.gradio-container .js-plotly-plot .legend .traces {cursor: pointer;}

/* My credit: larger, darker labels on the tiles, bars and lists */
.gradio-container .cc-tiles {gap: 14px;}
.gradio-container .cc-tile {border: 1.5px solid #cbd5e1; border-radius: 12px; padding: 14px 16px; gap: 6px;
           background: #ffffff;}
.gradio-container .cc-k {font-size: .98rem; font-weight: 600; color: #475569;}
.gradio-container .cc-v {font-size: 2rem; font-weight: 700;}
.gradio-container .cc-v small {font-size: 1rem; color: #475569;}
.gradio-container .cc-n {font-size: .95rem; color: #475569;}
.gradio-container .cc-goal {font-size: 1.05rem; color: #334155;}
.gradio-container .cc-pill {font-size: .9rem; font-weight: 600; padding: 2px 10px 2px 8px;}
.gradio-container .cc-row-top, .gradio-container .cc-debt {font-size: 1.02rem;}
.gradio-container .cc-amt {color: #475569;}
.gradio-container .cc-debt .cc-sub {font-size: .88rem; color: #475569;}
.gradio-container .cc-track, .gradio-container .cc-debt .cc-bar {height: 16px;}
.gradio-container .cc-legend {font-size: .95rem; color: #475569;}
.gradio-container .cc-note {font-size: .98rem; color: #475569;}
.gradio-container .cc-flag {font-size: .8rem;}
.gradio-container .cc-empty {border: 1.5px solid #cbd5e1; border-radius: 12px; font-size: 1.05rem;}
.gradio-container .cc-whatif-note {border-radius: 0 0 10px 10px;}
.gradio-container fieldset .info, .gradio-container span.info, .gradio-container div.info {font-size: .95rem !important;
           color: #475569 !important;}
"""
