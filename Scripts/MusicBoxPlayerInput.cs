using System.Collections.Generic;
using Godot;

namespace MusicBoxMod
{
    public sealed partial class MusicBoxEntry
    {
        private sealed partial class MenuPlayer
        {
            // Android popup Windows can fail in the host's subwindow focus path. Keep these
            // choices in the existing canvas instead; desktop OptionButtons are unchanged.
            private Control androidChoices;
            private void ConfigureAndroidSelector(OptionButton option)
            {
                if (OS.GetName() != "Android") return;
                option.FocusMode = Control.FocusModeEnum.None;
                option.MouseFilter = Control.MouseFilterEnum.Ignore;
                var opener = new Button { Name = "AndroidChoiceOpener", Flat = true, MouseFilter = Control.MouseFilterEnum.Stop };
                option.AddChild(opener);
                opener.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
                opener.Pressed += () => { if (!option.Disabled && CanInteract()) OpenAndroidChoices(option); };
            }
            private void CloseAndroidChoices()
            {
                if (androidChoices == null) return;
                androidChoices.Hide(); androidChoices.QueueFree(); androidChoices = null;
                ReleaseInputShield();
            }
            private void OpenAndroidChoices(OptionButton option)
            {
                CloseAndroidChoices();
                var overlay = new Control { Name = "AndroidMusicChoices", MouseFilter = Control.MouseFilterEnum.Stop };
                androidChoices = overlay; parent.AddChild(overlay);
                overlay.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
                var shade = new ColorRect { Color = new Color(0, 0, 0, .55f), MouseFilter = Control.MouseFilterEnum.Stop };
                overlay.AddChild(shade); shade.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
                shade.GuiInput += input => {
                    if (input is InputEventMouseButton { Pressed: true, ButtonIndex: MouseButton.Left })
                    { shade.AcceptEvent(); CloseAndroidChoices(); }
                };
                Vector2 size = new Vector2(560, 420).Min((parent.Size - new Vector2(24, 24)).Max(new Vector2(1, 1)));
                var panel = new PanelContainer { Position = (parent.Size - size) / 2, Size = size, MouseFilter = Control.MouseFilterEnum.Stop };
                panel.AddThemeStyleboxOverride("panel", ButtonStyle("101c22", "6da68c")); overlay.AddChild(panel);
                var box = new VBoxContainer(); panel.AddChild(box);
                var heading = new HBoxContainer(); box.AddChild(heading);
                var label = new Label { Text = option == tracks ? "选择歌曲" : "播放模式", SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
                heading.AddChild(label); label.AddThemeFontSizeOverride("font_size", 18);
                var close = new Button { Text = "关闭", CustomMinimumSize = new Vector2(64, 36) };
                StyleButton(close, false); heading.AddChild(close); close.Pressed += CloseAndroidChoices;
                var scroll = new ScrollContainer { SizeFlagsVertical = Control.SizeFlags.ExpandFill,
                    HorizontalScrollMode = ScrollContainer.ScrollMode.Disabled, FollowFocus = true };
                box.AddChild(scroll);
                var list = new VBoxContainer { SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
                scroll.AddChild(list);
                var listDrag = new PlayerDragGesture();
                int initialScroll = 0;
                Button selected = null;
                for (int index = 0; index < option.ItemCount; index++)
                {
                    int choiceIndex = index;
                    var item = new Button { Text = option.GetItemText(index), Alignment = HorizontalAlignment.Left,
                        TextOverrunBehavior = TextServer.OverrunBehavior.TrimEllipsis, CustomMinimumSize = new Vector2(0, 40),
                        SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
                    StyleButton(item, index == option.Selected); list.AddChild(item);
                    if (index == option.Selected) selected = item;
                    void Choose()
                    {
                        CloseAndroidChoices();
                        if (!CanInteract() || option.Disabled || choiceIndex >= option.ItemCount) return;
                        option.Select(choiceIndex);
                        option.EmitSignal(OptionButton.SignalName.ItemSelected, (long)choiceIndex);
                    }
                    // Do not save from Button.Pressed: Android's emulated mouse release also
                    // emits it after a swipe. Track the whole gesture in stable canvas coordinates.
                    item.GuiInput += input => {
                        if (input is InputEventMouseButton mouse && mouse.ButtonIndex == MouseButton.Left)
                        {
                            Vector2 point = item.GetGlobalTransformWithCanvas() * mouse.Position;
                            if (mouse.Pressed)
                            {
                                initialScroll = scroll.ScrollVertical;
                                listDrag.Begin(point, Vector2.Zero, new Vector2(8, 8));
                            }
                            else if (listDrag.Pressed)
                            {
                                listDrag.Move(point, out _);
                                bool tap = listDrag.End();
                                if (tap && new Rect2(Vector2.Zero, item.Size).HasPoint(mouse.Position)) Choose();
                            }
                            item.AcceptEvent();
                        }
                        else if (input is InputEventMouseMotion motion && listDrag.Pressed)
                        {
                            if (listDrag.Move(item.GetGlobalTransformWithCanvas() * motion.Position, out Vector2 delta))
                                scroll.ScrollVertical = initialScroll - Mathf.RoundToInt(delta.Y);
                            item.AcceptEvent();
                        }
                        else if (input is InputEventScreenTouch or InputEventScreenDrag)
                            item.AcceptEvent(); // The emulated mouse stream above owns this gesture.
                        else if (input is InputEventKey { Pressed: true, Echo: false, Keycode: Key.Space or Key.Enter })
                        { item.AcceptEvent(); Choose(); }
                    };
                }
                InstallPointerIsolation(overlay); CaptureSceneDragging();
                selected?.GrabFocus();
            }
            private readonly Dictionary<DragMenu, bool> shieldedMenus = new();
            private bool pointerOwned, inputShieldActive;
            private void InstallPointerIsolation(Node node)
            {
                if (node is Control control)
                {
                    control.GuiInput += ShieldPointerEvent;
                    control.MouseEntered += RefreshInputShield;
                    control.MouseExited += RefreshInputShield;
                }
                foreach (Node child in node.GetChildren()) InstallPointerIsolation(child);
            }
            private void ShieldPointerEvent(InputEvent input)
            {
                if (!CanInteract()) return;
                if (input is InputEventMouseButton mouse && mouse.ButtonIndex == MouseButton.Left)
                {
                    pointerOwned = mouse.Pressed;
                    if (mouse.Pressed) CaptureSceneDragging();
                    else RefreshInputShield();
                }
            }
            private void FindSceneDraggers(Node node)
            {
                if (node is DragMenu menu && !menu.IsQueuedForDeletion())
                {
                    shieldedMenus[menu] = menu.IsProcessingInput();
                    menu.mousePress = false;
                    menu.SetProcessInput(false);
                }
                foreach (Node child in node.GetChildren()) FindSceneDraggers(child);
            }
            private void CaptureSceneDragging()
            {
                if (!inputShieldActive) { inputShieldActive = true; FindSceneDraggers(tree.Root); }
                foreach (DragMenu menu in shieldedMenus.Keys)
                    if (GodotObject.IsInstanceValid(menu) && !menu.IsQueuedForDeletion())
                    { menu.mousePress = false; menu.SetProcessInput(false); }
            }
            private void ReleaseInputShield()
            {
                pointerOwned = false;
                foreach (var pair in shieldedMenus)
                    if (GodotObject.IsInstanceValid(pair.Key) && !pair.Key.IsQueuedForDeletion())
                    { pair.Key.mousePress = false; pair.Key.SetProcessInput(pair.Value); }
                shieldedMenus.Clear(); inputShieldActive = false;
            }
            private void RefreshInputShield()
            {
                if (disposed) return;
                if (!CanInteract() || !root.IsVisibleInTree() || !window.HasFocus()) { ReleaseInputShield(); return; }
                bool held = Input.IsMouseButtonPressed(MouseButton.Left);
                if (pointerOwned && !held && !gesture.Pressed) pointerOwned = false;
                Vector2 point = root.GetLocalMousePosition();
                bool hover = new Rect2(Vector2.Zero, root.Size).HasPoint(point)
                    && mask.GetBitv(new Vector2I((int)point.X, (int)point.Y));
                bool popup = androidChoices != null || tracks.GetPopup().Visible || orderSelector.GetPopup().Visible;
                // Do not steal an existing scene drag when its pointer merely crosses the player.
                if (pointerOwned || gesture.Pressed || popup || hover && !held) CaptureSceneDragging();
                else ReleaseInputShield();
            }
        }
    }
}
