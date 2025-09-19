// in custom_pan_box_tool.js
(function(root, factory) {
  factory(root.Bokeh);
}(this, function(Bokeh) {
  (function(root, factory) {
  factory(root.Bokeh);
}(this, function(Bokeh) {
  const define = Bokeh.define;
  const BoxSelectTool = Bokeh.Models('BoxSelectTool');
  const BoxSelectToolView = BoxSelectTool.prototype.default_view;
  const PanTool = Bokeh.Models('PanTool');
  const PanToolView = PanTool.prototype.default_view;

  var CustomPanBoxToolView = BoxSelectToolView.extend({
    _pan_start: function(ev) {
      if (ev.modifiers.shift) {
        BoxSelectToolView.prototype._pan_start.call(this, ev);
      } else {
        this.pan_view = new PanToolView({model: new PanTool(), parent: this.parent});
        this.pan_view.plot_view = this.plot_view;
        this.pan_view._pan_start(ev);
      }
    },

    _pan: function(ev) {
      if (ev.modifiers.shift) {
        BoxSelectToolView.prototype._pan.call(this, ev);
      } else if (this.pan_view) {
        this.pan_view._pan(ev);
      }
    },

    _pan_end: function(ev) {
      if (ev.modifiers.shift) {
        BoxSelectToolView.prototype._pan_end.call(this, ev);
      } else if (this.pan_view) {
        this.pan_view._pan_end(ev);
        this.pan_view = null;
      }
    },
  });

  var CustomPanBoxTool = BoxSelectTool.extend({
    default_view: CustomPanBoxToolView,
    type: "CustomPanBoxTool",
    tool_name: "Custom Pan/Box Select",
    icon: "bk-tool-icon-pan",
    event_type: "pan",
    default_order: 10,
  });

  define({
    CustomPanBoxTool: CustomPanBoxTool
  });
}));
}));
