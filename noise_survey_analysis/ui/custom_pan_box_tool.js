import {build_view} from "@bokehjs/core/build_views"
import {BoxSelectTool, BoxSelectToolView, PanTool} from "@bokehjs/models/tools/gestures"
import {register_models} from "@bokehjs/base"

export class CustomPanBoxToolView extends BoxSelectToolView {
  static __name__ = "CustomPanBoxToolView"
  static __module__ = "noise_survey_analysis.ui.custom_pan_box_tool"

  initialize() {
    super.initialize()
    this._pan_tool = null
    this._pan_view = null
  }

  async lazy_initialize() {
    await super.lazy_initialize()
    await this._create_pan_view()
  }

  remove() {
    this._pan_view?.remove()
    this._pan_view = null
    this._pan_tool = null
    super.remove()
  }

  connect_signals() {
    super.connect_signals()
    this.connect(this.model.properties.dimensions.change, () => {
      if (this._pan_tool != null) {
        this._pan_tool.dimensions = this.model.dimensions
      }
    })
  }

  async _create_pan_view() {
    if (this._pan_view != null) {
      this._pan_tool.dimensions = this.model.dimensions
      this._pan_view.plot_view = this.plot_view
      return
    }

    const pan_tool = new PanTool({dimensions: this.model.dimensions})
    const pan_view = await build_view(pan_tool, {parent: this.parent})
    pan_view.plot_view = this.plot_view

    this._pan_tool = pan_tool
    this._pan_view = pan_view
  }

  _use_box_select(ev) {
    return ev.modifiers.shift
  }

  _pan_start(ev) {
    if (this._use_box_select(ev)) {
      super._pan_start(ev)
      return
    }

    this._invoke_pan_view("_pan_start", ev)
  }

  _pan(ev) {
    if (this._use_box_select(ev)) {
      super._pan(ev)
      return
    }

    this._invoke_pan_view("_pan", ev)
  }

  _pan_end(ev) {
    if (this._use_box_select(ev)) {
      super._pan_end(ev)
      return
    }

    this._invoke_pan_view("_pan_end", ev)
  }

  _invoke_pan_view(method, ev) {
    const pan_view = this._pan_view
    if (pan_view == null) {
      return
    }

    if (this._pan_tool != null) {
      this._pan_tool.dimensions = this.model.dimensions
    }
    pan_view.plot_view = this.plot_view

    const fn = pan_view[method]
    if (typeof fn === "function") {
      fn.call(pan_view, ev)
    }
  }
}

export class CustomPanBoxTool extends BoxSelectTool {
  static __name__ = "CustomPanBoxTool"
  static __module__ = "noise_survey_analysis.ui.custom_pan_box_tool"

  constructor(attrs) {
    super(attrs)
    this.tool_name = "Custom Pan/Box Select"
    this.icon = "bk-tool-icon-pan"
    this.event_type = "pan"
    this.default_order = 10
  }
}

CustomPanBoxTool.prototype.default_view = CustomPanBoxToolView

register_models({CustomPanBoxTool})
